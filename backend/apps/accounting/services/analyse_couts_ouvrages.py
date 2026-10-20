"""
Analyse des coûts par ouvrage (modélisation dépenses vs recettes).

Objectif : départager les ouvrages gérés par Soakoja entre ceux qui coûtent le plus
et le moins à gérer, sur les 12 derniers mois complets (le mois calendaire en cours est
toujours exclu).

Postes de dépense agrégés par ouvrage :
  - salaires / charges sociales : lignes DiameX sur comptes "employé", rattachées à
    l'employé (par surnom / volet), puis ventilées sur ses ouvrages ;
  - véhicules : lignes DiameX sur comptes "véhicule" (carburant 606100/606107 + comptes
    cochés), rattachées au véhicule par la plaque puis au conducteur ;
  - ouvrage-direct : lignes DiameX sur comptes "nécessite ouvrage" OU "compte à répartir
    sur un ouvrage (analyse des coûts)" dont on extrait le nom de l'ouvrage du libellé
    (ex. 601011). Le second flag n'a aucun effet sur le contrôle DiameX ;
  - pièces planning : lignes PlanningDetail (montant > 0) rattachées à un ouvrage, hors
    dépenses antérieures au début de gestion de l'ouvrage (= construction). Restreint aux
    désignations "Bon de livraison" (type_avance_caissiere) : les désignations "Avance"
    (Prestation MI, Essence, Loyer, Repas, ...) sont exportées séparément vers DiameX et
    déjà comptées dans les postes salaires/véhicules/ouvrage-direct — les inclure ici les
    compterait deux fois.

Rattachement employé -> ouvrages : uniquement les liens FORMELS, càd la table
`EmployeOuvrages` (responsabilité datée) et `ModaliteGestion.employe`. La présence au
planning ne crée pas de lien (un technicien / la direction passe sur beaucoup d'ouvrages).
Si l'employé n'a aucun lien formel, on tente la descente hiérarchique (poste "hierarchie").

Clé de répartition des postes indirects (salaires, véhicules) entre les ouvrages rattachés
à un employé :  poids = alpha * part(jours de planning) + (1 - alpha) * part(points d'eau
publics hors BP).  Repli sur les points d'eau si aucune donnée de planning.

Cas particulier "Prestation MI" (compte 621101, libellé contenant "Prestation MI") :
prestations des postes Mpikojakoja ifotony. Répartie UNIQUEMENT sur les ouvrages
"Responsables ouvrages" (EmployeOuvrages) de l'employé, au prorata des points d'eau
publics (pas de jours de planning ici). Si l'un de ces ouvrages est le chef-lieu de sa
commune (nom identique, sauf "Vohilengo AEPG"), sa part est en outre répartie sur tous
les ouvrages de la commune, au même prorata (cf. repartir_prestation_mi).

NB v1 : la recette prévue est une approximation (montants des relevés pour le volume ;
tarif forfaitaire x trimestres pour le forfait) sans décote fine des coupures. Le
réalisé provient de DiameX (707401 + 748411).

Fenêtre RECETTES (réalisé + prévu) plus courte que celle des dépenses : en plus du mois
en cours, le dernier mois complet est aussi exclu (paiements/relevés souvent encore
incomplets à cette date), cf. `_date_fin_recettes` / `ContexteAnalyse.date_fin_recettes`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from apps.billing.tarifs_forfaitaires import tarif_depuis_valeurs

import pytz
from dateutil.relativedelta import relativedelta
from django.utils import timezone

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.accounting.models import BaseDiameX
from apps.billing.models import ModaliteGestion, PointEau, Releve
from apps.employees.models import Employe, EmployeOuvrages, HierarchieEmploye
from apps.organization.models import Organisation, Ouvrage
from apps.planning.models import Planning, PlanningDetail

TZ_MADAGASCAR = pytz.timezone("Indian/Antananarivo")

# Filtre grossier pour restreindre les lignes DiameX à l'organisation Soakoja.
SOAKOJA_FICHIER_SOURCE_MARQUEUR = "soakoja"

# Comptes carburant toujours considérés comme "véhicule" même sans case cochée.
COMPTES_CARBURANT = ("606100", "606107")

# Comptes de recette exploitation eau (réalisé).
COMPTE_RECETTE_VOLUME = "707401"
COMPTE_RECETTE_FORFAIT = "748411"

# Tâches de planning à ignorer dans le décompte des "jours dépensés" par ouvrage.
TACHES_PLANNING_HORS_TERRAIN = (
    "repos",
    "congé",
    "conge",
    "jour férié",
    "jour ferie",
    "récupération",
    "recuperation",
    "permission",
)

MODALITES_FORFAIT = ("forfaitaire", "mixte")

DEFAULT_ALPHA = Decimal("0.5")
D0 = Decimal("0")

# Compte 621101 : lignes "Prestation MI" = prestations des Mpikojakoja ifotony.
# Répartition dédiée (cf. repartir_prestation_mi) : uniquement sur les ouvrages
# "Responsables ouvrages" (EmployeOuvrages) de l'employé, au prorata des points d'eau
# publics, avec expansion sur toute la commune si l'ouvrage responsable en est le chef-lieu.
COMPTE_PRESTATION_MI = "621101"
MARQUEUR_PRESTATION_MI = "prestation mi"

# Exception à la détection de chef-lieu (nom ouvrage == nom commune) : cet ouvrage porte
# le nom de sa commune (Vohilengo) sans en être le chef-lieu.
OUVRAGE_EXCEPTION_CHEF_LIEU = "vohilengo aepg"

# Pièces planning (PlanningDetail) : ne retenir QUE les lignes "Bon de livraison". Les
# désignations de type "Avance" (Prestation MI, Essence, Loyer, Repas, ...) sont exportées
# séparément en DiameX (comptes employé/véhicule/ouvrage) et seraient sinon comptées deux fois.
# NB : Designation.type_avance_caissiere stocke le LIBELLÉ ("Bon de livraison", "Avance",
# "Recette"), pas la clé de TYPE_AVANCE_CHOICES ("bon_livraison", ...) — comparer en iexact.
TYPE_AVANCE_BON_LIVRAISON = "Bon de livraison"

# Pondération du score de criticité (cf. calculer_indicateurs_financiers) : le ratio de
# charges (dépenses / recettes encaissées) pèse plus lourd que le taux d'impayés, car un
# ouvrage structurellement déficitaire en trésorerie est plus grave qu'un ouvrage qui
# facture correctement mais tarde à être payé.
POIDS_SCORE_RATIO_CHARGES = Decimal("0.6")
POIDS_SCORE_TAUX_IMPAYES = Decimal("0.4")


# --------------------------------------------------------------------------- #
# Période                                                                     #
# --------------------------------------------------------------------------- #
def resoudre_periode(reference: date | None = None) -> tuple[date, date]:
    """Retourne (date_debut, date_fin) = 12 derniers mois complets.

    date_fin = dernier jour du mois précédant le mois de `reference` (aujourd'hui par
    défaut). date_debut = premier jour, 12 mois avant date_fin.
    """
    today = reference or timezone.localdate()
    premier_du_mois_courant = today.replace(day=1)
    date_fin = premier_du_mois_courant - relativedelta(days=1)
    date_debut = (premier_du_mois_courant - relativedelta(months=12))
    return date_debut, date_fin


def _date_fin_recettes(date_fin: date) -> date:
    """Pour les recettes uniquement, on exclut EN PLUS le dernier mois complet (pas
    seulement le mois en cours) : les paiements DiameX et relevés de ce mois arrivent
    encore souvent avec retard et donneraient un montant sous-estimé et trompeur.
    Retourne le dernier jour du mois précédant celui de `date_fin`."""
    premier_du_mois = date_fin.replace(day=1)
    return premier_du_mois - relativedelta(days=1)


def _to_local_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return value.astimezone(TZ_MADAGASCAR).date()
        return value.date()
    return value


# --------------------------------------------------------------------------- #
# Paramètres de modélisation                                                  #
# --------------------------------------------------------------------------- #
@dataclass
class ParamsAnalyse:
    alpha: Decimal = DEFAULT_ALPHA
    inc_salaires: bool = True
    inc_salaires_hierarchie: bool = True
    inc_vehicules: bool = True
    inc_vehicules_hierarchie: bool = True
    inc_ouvrage_direct: bool = True
    inc_pieces: bool = True
    repartir_non_affecte: bool = False
    base_id: str = ""
    region_id: str = ""
    district_id: str = ""
    commune_id: str = ""

    @classmethod
    def from_request(cls, request) -> "ParamsAnalyse":
        get = request.GET.get

        def _bool(name, default=True):
            raw = get(name)
            if raw is None:
                return default
            return str(raw).lower() in ("1", "true", "on", "yes", "oui")

        try:
            alpha = Decimal(str(get("alpha", "0.5")))
        except Exception:
            alpha = DEFAULT_ALPHA
        alpha = max(D0, min(Decimal("1"), alpha))

        return cls(
            alpha=alpha,
            inc_salaires=_bool("inc_salaires"),
            inc_salaires_hierarchie=_bool("inc_salaires_hierarchie"),
            inc_vehicules=_bool("inc_vehicules"),
            inc_vehicules_hierarchie=_bool("inc_vehicules_hierarchie"),
            inc_ouvrage_direct=_bool("inc_ouvrage_direct"),
            inc_pieces=_bool("inc_pieces"),
            repartir_non_affecte=_bool("repartir_non_affecte", default=False),
            base_id=(get("base") or "").strip(),
            region_id=(get("region") or "").strip(),
            district_id=(get("district") or "").strip(),
            commune_id=(get("commune") or "").strip(),
        )


# --------------------------------------------------------------------------- #
# Contexte (données préchargées une fois)                                     #
# --------------------------------------------------------------------------- #
@dataclass
class ContexteAnalyse:
    date_debut: date
    date_fin: date
    date_fin_recettes: date = None  # dépenses: jusqu'à date_fin ; recettes: un mois de moins
    base_id: str = ""
    base_volet: str = ""
    ouvrage_ids: set = field(default_factory=set)
    ouvrages_by_id: dict = field(default_factory=dict)
    modalite_by_ouvrage: dict = field(default_factory=dict)  # ouvrage_id -> ModaliteGestion
    pe_public_by_ouvrage: dict = field(default_factory=dict)  # ouvrage_id -> int
    jours_planning_by_ouvrage: dict = field(default_factory=dict)  # ouvrage_id -> int
    jours_emp_ouvrage: dict = field(default_factory=dict)  # (employe_id, ouvrage_id) -> int
    employe_ouvrages_by_emp: dict = field(default_factory=dict)  # employe_id -> set(ouvrage_id)
    modalite_ouvrages_by_emp: dict = field(default_factory=dict)  # employe_id -> set(ouvrage_id)
    subordonnes_by_emp: dict = field(default_factory=dict)  # employe_id -> set(employe_id)
    employe_by_surnom: dict = field(default_factory=dict)  # surnom_lower -> Employe
    employe_ids_scope: set = field(default_factory=set)  # ids employés dans le périmètre (org/base)
    soakoja_org_ids: list = field(default_factory=list)
    commune_by_ouvrage: dict = field(default_factory=dict)  # ouvrage_id -> commune_id (approximation: 1re commune trouvée)
    commune_nom_by_id: dict = field(default_factory=dict)  # commune_id -> nom_commune
    ouvrages_by_commune: dict = field(default_factory=dict)  # commune_id -> set(ouvrage_id)
    district_by_ouvrage: dict = field(default_factory=dict)  # ouvrage_id -> district_id
    district_nom_by_id: dict = field(default_factory=dict)  # district_id -> nom_district
    region_by_ouvrage: dict = field(default_factory=dict)  # ouvrage_id -> region_id
    region_nom_by_id: dict = field(default_factory=dict)  # region_id -> nom_region
    district_by_commune: dict = field(default_factory=dict)  # commune_id -> district_id
    region_by_district: dict = field(default_factory=dict)  # district_id -> region_id
    filtre_region_id: str = ""
    filtre_district_id: str = ""
    filtre_commune_id: str = ""


def _soakoja_org_ids() -> list:
    ids = list(
        Organisation.objects.filter(
            nom_organisation__icontains="soakoja"
        ).values_list("id", flat=True)
    )
    return ids


def _scope_diamex(qs, base_volet: str = ""):
    """Restreint un queryset BaseDiameX aux lignes Soakoja (marqueur fichier source),
    et à une base précise via son volet (colonnes Activ / Prog) si fourni."""
    from django.db.models import Q

    qs = qs.filter(fichier_source__icontains=SOAKOJA_FICHIER_SOURCE_MARQUEUR)
    if base_volet:
        qs = qs.filter(Q(activ__iexact=base_volet) | Q(prog__iexact=base_volet))
    return qs


def _planning_dans_periode(planning_rows, d1: date, d2: date):
    """Filtre en Python les plannings dont la date locale tombe dans [d1, d2]."""
    for row in planning_rows:
        local = _to_local_date(row["date"])
        if local and d1 <= local <= d2:
            yield row, local


def options_geo_soakoja() -> dict:
    """Régions / districts / communes parmi les ouvrages actuellement gérés par Soakoja
    (indépendant de la période), pour peupler les filtres géographiques des pages
    d'analyse. Chaque district porte son region_id, chaque commune son district_id
    (pour un filtrage en cascade côté frontend)."""
    soakoja_ids = _soakoja_org_ids()
    ouvrage_ids = set(
        ModaliteGestion.objects.filter(
            gestionnaire_id__in=soakoja_ids, date_fin__isnull=True
        ).values_list("ouvrage_id", flat=True)
    )
    rows = (
        PointEau.objects.filter(ouvrage_id__in=ouvrage_ids)
        .values(
            "parcelle__village__fokontany__commune_id",
            "parcelle__village__fokontany__commune__nom_commune",
            "parcelle__village__fokontany__commune__district_id",
            "parcelle__village__fokontany__commune__district__nom_district",
            "parcelle__village__fokontany__commune__district__region_id",
            "parcelle__village__fokontany__commune__district__region__nom_region",
        )
        .distinct()
    )
    regions, districts, communes = {}, {}, {}
    for row in rows:
        cid = row.get("parcelle__village__fokontany__commune_id")
        did = row.get("parcelle__village__fokontany__commune__district_id")
        rid = row.get("parcelle__village__fokontany__commune__district__region_id")
        if rid:
            regions[str(rid)] = row.get(
                "parcelle__village__fokontany__commune__district__region__nom_region"
            ) or ""
        if did:
            districts[str(did)] = {
                "nom": row.get("parcelle__village__fokontany__commune__district__nom_district") or "",
                "region_id": str(rid) if rid else "",
            }
        if cid:
            communes[str(cid)] = {
                "nom": row.get("parcelle__village__fokontany__commune__nom_commune") or "",
                "district_id": str(did) if did else "",
            }
    return {
        "regions": sorted(({"id": k, "nom": v} for k, v in regions.items()), key=lambda x: x["nom"]),
        "districts": sorted(({"id": k, **v} for k, v in districts.items()), key=lambda x: x["nom"]),
        "communes": sorted(({"id": k, **v} for k, v in communes.items()), key=lambda x: x["nom"]),
    }


def charger_contexte(
    d1: date, d2: date, base_id: str = "",
    region_id: str = "", district_id: str = "", commune_id: str = "",
) -> ContexteAnalyse:
    ctx = ContexteAnalyse(date_debut=d1, date_fin=d2, date_fin_recettes=_date_fin_recettes(d2))
    ctx.soakoja_org_ids = _soakoja_org_ids()

    base_id = (base_id or "").strip()
    if base_id and base_id not in ("all", "tous", ""):
        from apps.organization.models import Base

        base = Base.objects.filter(
            id=base_id, organisation_id__in=ctx.soakoja_org_ids
        ).first()
        if base:
            ctx.base_id = str(base.id)
            ctx.base_volet = (base.volet or "").strip()
    else:
        base_id = ""

    # --- Ouvrages Soakoja : via modalités de gestion actives aujourd'hui --- #
    modalites = (
        ModaliteGestion.objects.filter(gestionnaire_id__in=ctx.soakoja_org_ids)
        .filter(date_debut__lte=d2)
        .filter(date_fin__isnull=True)
        .select_related("ouvrage")
        .order_by("ouvrage_id", "date_debut")
    )
    if ctx.base_id:
        # Ouvrages rattachés à la base = ceux dont l'agent responsable (modalité) est de cette base
        modalites = modalites.filter(employe__base_id=ctx.base_id)
    for modalite in modalites:
        ctx.ouvrage_ids.add(modalite.ouvrage_id)
        ctx.ouvrages_by_id.setdefault(modalite.ouvrage_id, modalite.ouvrage)
        ctx.modalite_by_ouvrage.setdefault(modalite.ouvrage_id, modalite)
        if modalite.employe_id:
            ctx.modalite_ouvrages_by_emp.setdefault(modalite.employe_id, set()).add(
                modalite.ouvrage_id
            )

    # --- Géographie de chaque ouvrage (via ses points d'eau) --- #
    # Chaîne : Ouvrage -> PointEau -> Parcelle -> Village -> Fokontany -> Commune -> District -> Région.
    # Approximation : on retient la géo du premier point d'eau trouvé pour l'ouvrage.
    vus_geo = set()
    pe_geo_rows = (
        PointEau.objects.filter(ouvrage_id__in=ctx.ouvrage_ids)
        .exclude(ouvrage_id__isnull=True)
        .values(
            "ouvrage_id",
            "parcelle__village__fokontany__commune_id",
            "parcelle__village__fokontany__commune__nom_commune",
            "parcelle__village__fokontany__commune__district_id",
            "parcelle__village__fokontany__commune__district__nom_district",
            "parcelle__village__fokontany__commune__district__region_id",
            "parcelle__village__fokontany__commune__district__region__nom_region",
        )
    )
    for row in pe_geo_rows:
        oid = row["ouvrage_id"]
        if oid in vus_geo:
            continue
        commune_id_ouvrage = row.get("parcelle__village__fokontany__commune_id")
        if not commune_id_ouvrage:
            continue
        vus_geo.add(oid)
        district_id_ouvrage = row.get("parcelle__village__fokontany__commune__district_id")
        region_id_ouvrage = row.get("parcelle__village__fokontany__commune__district__region_id")

        ctx.commune_by_ouvrage[oid] = commune_id_ouvrage
        ctx.commune_nom_by_id[commune_id_ouvrage] = row.get(
            "parcelle__village__fokontany__commune__nom_commune"
        ) or ""
        ctx.ouvrages_by_commune.setdefault(commune_id_ouvrage, set()).add(oid)

        if district_id_ouvrage:
            ctx.district_by_ouvrage[oid] = district_id_ouvrage
            ctx.district_nom_by_id[district_id_ouvrage] = row.get(
                "parcelle__village__fokontany__commune__district__nom_district"
            ) or ""
            ctx.district_by_commune[commune_id_ouvrage] = district_id_ouvrage

        if region_id_ouvrage:
            ctx.region_by_ouvrage[oid] = region_id_ouvrage
            ctx.region_nom_by_id[region_id_ouvrage] = row.get(
                "parcelle__village__fokontany__commune__district__region__nom_region"
            ) or ""
            if district_id_ouvrage:
                ctx.region_by_district[district_id_ouvrage] = region_id_ouvrage

    # --- Filtre géographique (région / district / commune) --- #
    region_id = str(region_id or "").strip()
    district_id = str(district_id or "").strip()
    commune_id = str(commune_id or "").strip()
    if commune_id:
        ctx.ouvrage_ids = {o for o in ctx.ouvrage_ids if str(ctx.commune_by_ouvrage.get(o)) == commune_id}
    elif district_id:
        ctx.ouvrage_ids = {o for o in ctx.ouvrage_ids if str(ctx.district_by_ouvrage.get(o)) == district_id}
    elif region_id:
        ctx.ouvrage_ids = {o for o in ctx.ouvrage_ids if str(ctx.region_by_ouvrage.get(o)) == region_id}
    ctx.filtre_region_id = region_id
    ctx.filtre_district_id = district_id
    ctx.filtre_commune_id = commune_id

    # --- Points d'eau publics hors BP (actifs) --- #
    pe_rows = (
        PointEau.objects.filter(
            ouvrage_id__in=ctx.ouvrage_ids,
            datebranchement__isnull=False,
        )
        .exclude(type_point_eau__nom_type__icontains="privé")
        .exclude(type_point_eau__nom_type__icontains="prive")
        .exclude(type_point_eau__nom_type__iexact="bp")
        .exclude(datearretbranchement__isnull=False)
        .values_list("ouvrage_id", flat=True)
    )
    for ouvrage_id in pe_rows:
        ctx.pe_public_by_ouvrage[ouvrage_id] = ctx.pe_public_by_ouvrage.get(ouvrage_id, 0) + 1

    # --- Jours de planning par ouvrage (et par employé x ouvrage) --- #
    planning_rows = list(
        Planning.objects.filter(
            ouvrage_id__in=ctx.ouvrage_ids,
            employe_id__isnull=False,
            date__date__gte=d1 - relativedelta(days=2),
            date__date__lte=d2 + relativedelta(days=2),
        )
        .select_related("fiche_poste", "type_activite")
        .values("employe_id", "ouvrage_id", "date", "fiche_poste__tache", "type_activite__nomtype")
    )
    for row, _local in _planning_dans_periode(planning_rows, d1, d2):
        libelle = " ".join(
            str(row.get(k) or "") for k in ("fiche_poste__tache", "type_activite__nomtype")
        ).lower()
        if any(mot in libelle for mot in TACHES_PLANNING_HORS_TERRAIN):
            continue
        ouvrage_id = row["ouvrage_id"]
        emp_id = row["employe_id"]
        ctx.jours_planning_by_ouvrage[ouvrage_id] = (
            ctx.jours_planning_by_ouvrage.get(ouvrage_id, 0) + 1
        )
        ctx.jours_emp_ouvrage[(emp_id, ouvrage_id)] = (
            ctx.jours_emp_ouvrage.get((emp_id, ouvrage_id), 0) + 1
        )

    # --- Responsabilités EmployeOuvrages actives sur la période --- #
    for eo in EmployeOuvrages.objects.filter(
        ouvrage_id__in=ctx.ouvrage_ids, date_debut__lte=d2
    ).filter(models_q_actif(d1)):
        ctx.employe_ouvrages_by_emp.setdefault(eo.employe_id, set()).add(eo.ouvrage_id)

    # --- Hiérarchie : subordonnés directs actifs --- #
    today = timezone.localdate()
    for rel in HierarchieEmploye.objects.filter(date_debut__lte=today).filter(
        models_q_actif_date_fin(today)
    ).values("employe_id", "superieur_id"):
        ctx.subordonnes_by_emp.setdefault(rel["superieur_id"], set()).add(rel["employe_id"])

    # --- Index employés (Soakoja, ou base précise) par surnom --- #
    emp_qs = Employe.objects.filter(base__organisation_id__in=ctx.soakoja_org_ids)
    if ctx.base_id:
        emp_qs = emp_qs.filter(base_id=ctx.base_id)
    for emp in emp_qs.select_related("base"):
        ctx.employe_ids_scope.add(emp.id)
        if emp.surnom:
            ctx.employe_by_surnom[emp.surnom.strip().lower()] = emp

    return ctx


def models_q_actif(d1: date):
    from django.db.models import Q

    return Q(date_fin__isnull=True) | Q(date_fin__gte=d1)


def models_q_actif_date_fin(ref: date):
    from django.db.models import Q

    return Q(date_fin__isnull=True) | Q(date_fin__gte=ref)


# --------------------------------------------------------------------------- #
# Poids de répartition                                                        #
# --------------------------------------------------------------------------- #
def _parts(valeurs: dict) -> dict:
    total = sum(valeurs.values())
    if not total:
        return {}
    return {k: Decimal(str(v)) / Decimal(str(total)) for k, v in valeurs.items()}


def poids_ouvrages(ctx: ContexteAnalyse, alpha: Decimal) -> dict:
    """poids global par ouvrage = alpha * part(jours planning) + (1-alpha) * part(PE)."""
    part_planning = _parts(ctx.jours_planning_by_ouvrage)
    part_pe = _parts(ctx.pe_public_by_ouvrage)
    if not part_planning:
        return {oid: part_pe.get(oid, D0) for oid in ctx.ouvrage_ids}
    poids = {}
    for oid in ctx.ouvrage_ids:
        poids[oid] = alpha * part_planning.get(oid, D0) + (Decimal("1") - alpha) * part_pe.get(
            oid, D0
        )
    return poids


def _ouvrages_directs_de_employe(ctx: ContexteAnalyse, employe_id) -> set:
    """Ouvrages dont l'employé est FORMELLEMENT responsable : responsabilité datée
    (`EmployeOuvrages`) ou modalité de gestion à son nom (`ModaliteGestion.employe`).

    La simple présence au planning ne crée PAS de lien direct (un technicien ou la
    direction passe sur beaucoup d'ouvrages sans en être responsable) : le planning ne
    sert qu'à pondérer la répartition entre ouvrages déjà rattachés."""
    ids = set()
    ids |= ctx.employe_ouvrages_by_emp.get(employe_id, set())
    ids |= ctx.modalite_ouvrages_by_emp.get(employe_id, set())
    return ids & ctx.ouvrage_ids


def _ouvrages_hierarchie_de_employe(ctx: ContexteAnalyse, employe_id, _profondeur=0, _vus=None) -> set:
    """Ouvrages atteints uniquement en descendant sur les subordonnés (chef / direction
    sans ouvrage direct)."""
    if _vus is None:
        _vus = {employe_id}
    ids = set()
    if _profondeur >= 5:
        return ids
    for sub_id in ctx.subordonnes_by_emp.get(employe_id, set()):
        if sub_id in _vus:
            continue
        _vus.add(sub_id)
        ids |= _ouvrages_directs_de_employe(ctx, sub_id)
        ids |= _ouvrages_hierarchie_de_employe(ctx, sub_id, _profondeur + 1, _vus)
    return ids & ctx.ouvrage_ids


def _ouvrages_de_employe(ctx: ContexteAnalyse, employe_id):
    """Retourne (ouvrage_ids, mode) où mode ∈ {'direct', 'hierarchie', 'aucun'}."""
    directs = _ouvrages_directs_de_employe(ctx, employe_id)
    if directs:
        return directs, "direct"
    hier = _ouvrages_hierarchie_de_employe(ctx, employe_id)
    if hier:
        return hier, "hierarchie"
    return set(), "aucun"


def _ouvrage_sous_gestion_a(ctx: ContexteAnalyse, oid, ref_date) -> bool:
    """True si l'ouvrage est déjà géré par Soakoja à la date donnée (date_debut de la
    modalité active). Sans modalité ou sans date_debut : considéré géré."""
    modalite = ctx.modalite_by_ouvrage.get(oid)
    debut = getattr(modalite, "date_debut", None)
    if not debut or ref_date is None:
        return True
    return _to_local_date(ref_date) >= debut


def repartir_cout_employe(
    ctx: ContexteAnalyse, montant: Decimal, employe_id, alpha: Decimal, ref_date=None
):
    """Ventile `montant` sur les ouvrages de l'employé selon le blend planning / PE.
    Retourne (ventilation, mode). ventilation == {} si aucun ouvrage rattachable.
    Les ouvrages pas encore sous gestion Soakoja à `ref_date` sont écartés."""
    ouvrage_ids, mode = _ouvrages_de_employe(ctx, employe_id)
    if ref_date is not None:
        ouvrage_ids = {o for o in ouvrage_ids if _ouvrage_sous_gestion_a(ctx, o, ref_date)}
    if not ouvrage_ids:
        return {}, mode

    jours = {
        oid: ctx.jours_emp_ouvrage.get((employe_id, oid), 0) for oid in ouvrage_ids
    }
    pe = {oid: ctx.pe_public_by_ouvrage.get(oid, 0) for oid in ouvrage_ids}
    part_jours = _parts(jours)
    part_pe = _parts(pe)

    if not part_jours and not part_pe:
        # aucun critère : répartition égale
        n = len(ouvrage_ids)
        return {oid: montant / n for oid in ouvrage_ids}, mode
    if not part_jours:
        poids = part_pe
    elif not part_pe:
        poids = part_jours
    else:
        poids = {
            oid: alpha * part_jours.get(oid, D0) + (Decimal("1") - alpha) * part_pe.get(oid, D0)
            for oid in ouvrage_ids
        }

    total_poids = sum(poids.values()) or Decimal("1")
    return {oid: montant * (p / total_poids) for oid, p in poids.items()}, mode


# --------------------------------------------------------------------------- #
# Postes de dépense                                                           #
# --------------------------------------------------------------------------- #
def _diamex_periode(ctx: "ContexteAnalyse", qs):
    from django.db.models import Q

    d1, d2 = ctx.date_debut, ctx.date_fin
    return _scope_diamex(qs, ctx.base_volet).filter(
        Q(date_rec__range=(d1, d2))
        | (Q(date_rec__isnull=True) & Q(date_m__range=(d1, d2)))
    )


def _diamex_periode_recettes(ctx: "ContexteAnalyse", qs):
    """Comme `_diamex_periode`, mais bornée à `ctx.date_fin_recettes` (recettes
    uniquement : on exclut aussi le dernier mois complet, pas seulement le mois en cours)."""
    from django.db.models import Q

    d1, d2 = ctx.date_debut, ctx.date_fin_recettes
    return _scope_diamex(qs, ctx.base_volet).filter(
        Q(date_rec__range=(d1, d2))
        | (Q(date_rec__isnull=True) & Q(date_m__range=(d1, d2)))
    )


def _est_prestation_mi(compte_code: str, description: str) -> bool:
    """Ligne 621101 dont le libellé contient 'Prestation MI' (prestations des postes
    Mpikojakoja ifotony) -> répartition dédiée (cf. repartir_prestation_mi)."""
    if (compte_code or "") != COMPTE_PRESTATION_MI:
        return False
    return MARQUEUR_PRESTATION_MI in _normaliser_texte(description)


def _est_chef_lieu(ctx: ContexteAnalyse, ouvrage_id) -> bool:
    """True si l'ouvrage porte le même nom que sa commune (chef-lieu), à l'exception
    explicite de « Vohilengo AEPG » (dans la commune de Vohilengo, mais pas son chef-lieu)."""
    ouvrage = ctx.ouvrages_by_id.get(ouvrage_id)
    if not ouvrage:
        return False
    nom_ouvrage = _normaliser_texte(getattr(ouvrage, "nom_ouvrage", "")).strip()
    if not nom_ouvrage or nom_ouvrage == OUVRAGE_EXCEPTION_CHEF_LIEU:
        return False
    commune_id = ctx.commune_by_ouvrage.get(ouvrage_id)
    if not commune_id:
        return False
    nom_commune = _normaliser_texte(ctx.commune_nom_by_id.get(commune_id, "")).strip()
    return bool(nom_commune) and nom_ouvrage == nom_commune


def repartir_prestation_mi(ctx: ContexteAnalyse, montant: Decimal, employe_id) -> dict:
    """Ventile une ligne 'Prestation MI' (621101) sur les ouvrages dont l'employé
    (poste Mpikojakoja ifotony) est responsable via « Responsables ouvrages »
    (EmployeOuvrages uniquement — pas modalité ni hiérarchie), au prorata des points
    d'eau publics hors BP. Si un ouvrage responsable est le chef-lieu de sa commune, la
    part qui lui revient est en outre répartie sur tous les ouvrages de la commune
    (même prorata), le Mpikojakoja du chef-lieu couvrant toute la commune."""
    directs = ctx.employe_ouvrages_by_emp.get(employe_id, set()) & ctx.ouvrage_ids
    if not directs:
        return {}

    pe = {oid: ctx.pe_public_by_ouvrage.get(oid, 0) for oid in directs}
    part = _parts(pe)
    if not part:
        n = len(directs)
        part = {oid: Decimal("1") / n for oid in directs}

    ventilation = defaultdict(lambda: D0)
    for oid, p in part.items():
        montant_oid = montant * p
        if _est_chef_lieu(ctx, oid):
            commune_id = ctx.commune_by_ouvrage.get(oid)
            ouvrages_commune = (ctx.ouvrages_by_commune.get(commune_id, set()) & ctx.ouvrage_ids) or {oid}
            pe_commune = {o: ctx.pe_public_by_ouvrage.get(o, 0) for o in ouvrages_commune}
            part_commune = _parts(pe_commune)
            if not part_commune:
                n_commune = len(ouvrages_commune)
                part_commune = {o: Decimal("1") / n_commune for o in ouvrages_commune}
            for o, pc in part_commune.items():
                ventilation[o] += montant_oid * pc
        else:
            ventilation[oid] += montant_oid
    return dict(ventilation)


def depenses_salaires_charges(ctx: ContexteAnalyse, alpha: Decimal):
    """Retourne (direct, hierarchie, non_affecte) : deux maps ouvrage_id -> montant selon
    que l'employé est responsable direct de l'ouvrage ou seulement via la hiérarchie.

    Cas particulier : les lignes du compte 621101 contenant « Prestation MI » suivent une
    répartition dédiée (`repartir_prestation_mi`), toujours comptée en « direct »."""
    par_direct = defaultdict(lambda: D0)
    par_hier = defaultdict(lambda: D0)
    non_affecte = D0

    rows = (
        _diamex_periode(
            ctx,
            BaseDiameX.objects.filter(compte__employe_obligatoire=True, montant_out__gt=0),
        )
        .select_related("compte")
        .values("montant_out", "detail", "pers", "date_rec", "date_m", "compte_code", "description")
    )
    for row in rows:
        montant = Decimal(str(row["montant_out"] or 0))
        if montant <= 0:
            continue
        cle = (row.get("detail") or row.get("pers") or "").strip().lower()
        employe = ctx.employe_by_surnom.get(cle)
        if not employe:
            non_affecte += montant
            continue
        ref_date = row.get("date_rec") or row.get("date_m")

        if _est_prestation_mi(row.get("compte_code"), row.get("description")):
            ventilation = repartir_prestation_mi(ctx, montant, employe.id)
            if not ventilation:
                non_affecte += montant
                continue
            for oid, part in ventilation.items():
                par_direct[oid] += part
            continue

        ventilation, mode = repartir_cout_employe(ctx, montant, employe.id, alpha, ref_date)
        if not ventilation:
            non_affecte += montant
            continue
        cible = par_hier if mode == "hierarchie" else par_direct
        for oid, part in ventilation.items():
            cible[oid] += part
    return dict(par_direct), dict(par_hier), non_affecte


def _normalize_plate(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def depenses_vehicules(ctx: ContexteAnalyse, alpha: Decimal):
    """Retourne (direct, hierarchie, non_affecte) selon le rattachement du conducteur."""
    from django.db.models import Q

    from apps.inventory.models_vehicles import AffectationVehicule, Vehicule

    par_direct = defaultdict(lambda: D0)
    par_hier = defaultdict(lambda: D0)
    non_affecte = D0

    vehicules = list(Vehicule.objects.all().values("id", "immatriculation"))
    plate_index = sorted(
        ((v["id"], _normalize_plate(v["immatriculation"])) for v in vehicules if v["immatriculation"]),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    affectations = list(
        AffectationVehicule.objects.all().values(
            "vehicule_id", "employe_id", "date_debut", "date_fin"
        )
    )
    aff_by_vehicule = defaultdict(list)
    for aff in affectations:
        aff_by_vehicule[aff["vehicule_id"]].append(aff)

    rows = (
        _diamex_periode(
            ctx,
            BaseDiameX.objects.filter(montant_out__gt=0).filter(
                Q(compte__compte_vehicule=True) | Q(compte_code__in=COMPTES_CARBURANT)
            ),
        )
        .select_related("compte")
        .values("montant_out", "detail", "description", "info", "date_rec", "date_m")
    )
    for row in rows:
        montant = Decimal(str(row["montant_out"] or 0))
        if montant <= 0:
            continue
        texte = _normalize_plate(
            f"{row.get('detail') or ''} {row.get('description') or ''} {row.get('info') or ''}"
        )
        vehicule_id = next((vid for vid, plate in plate_index if plate and plate in texte), None)
        if not vehicule_id:
            non_affecte += montant
            continue
        ref_date = row.get("date_rec") or row.get("date_m")
        conducteur_id = None
        for aff in aff_by_vehicule.get(vehicule_id, []):
            debut = aff["date_debut"]
            fin = aff["date_fin"]
            if debut and ref_date and debut <= ref_date and (fin is None or fin >= ref_date):
                conducteur_id = aff["employe_id"]
                break
        if not conducteur_id or conducteur_id not in ctx.employe_ids_scope:
            non_affecte += montant
            continue
        ventilation, mode = repartir_cout_employe(ctx, montant, conducteur_id, alpha, ref_date)
        if not ventilation:
            non_affecte += montant
            continue
        cible = par_hier if mode == "hierarchie" else par_direct
        for oid, part in ventilation.items():
            cible[oid] += part
    return dict(par_direct), dict(par_hier), non_affecte


def _normaliser_texte(value: str) -> str:
    import unicodedata

    txt = unicodedata.normalize("NFKD", str(value or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return " " + " ".join(txt.lower().split()) + " "


def _index_noms_ouvrages(ctx: ContexteAnalyse):
    """Liste (ouvrage_id, nom_normalisé) triée par longueur décroissante pour un scan
    de libellé (repli quand l'extracteur dédié ne trouve rien, ex. compte 601011)."""
    index = []
    for oid, ouvrage in ctx.ouvrages_by_id.items():
        nom = _normaliser_texte(getattr(ouvrage, "nom_ouvrage", "")).strip()
        if len(nom) >= 4:
            index.append((oid, nom))
    index.sort(key=lambda item: len(item[1]), reverse=True)
    return index


def _ouvrage_depuis_libelle(description: str, index):
    texte = _normaliser_texte(description)
    for oid, nom in index:
        if f" {nom} " in texte:
            return oid
    return None


def depenses_ouvrage_direct(ctx: ContexteAnalyse):
    par_ouvrage = defaultdict(lambda: D0)
    non_affecte = D0
    index_noms = _index_noms_ouvrages(ctx)

    from django.db.models import Q

    rows = (
        _diamex_periode(
            ctx,
            BaseDiameX.objects.filter(montant_out__gt=0)
            .filter(
                Q(compte__necessite_ouvrage=True) | Q(compte__compte_ouvrage_analyse=True)
            )
            .exclude(compte__employe_obligatoire=True)
            .exclude(compte__compte_vehicule=True),
        )
        .select_related("compte")
        .values("montant_out", "description", "compte_code", "date_rec", "date_m")
    )
    for row in rows:
        montant = Decimal(str(row["montant_out"] or 0))
        if montant <= 0:
            continue
        ref_date = row.get("date_rec") or row.get("date_m")
        extraction = extraire_ouvrage_et_mois_generique(
            row.get("description") or "", row.get("compte_code") or ""
        )
        if isinstance(extraction, list):
            candidats = [e for e in extraction if e and e.get("ouvrage_obj")]
        else:
            candidats = [extraction] if extraction and extraction.get("ouvrage_obj") else []
        cibles = [
            e["ouvrage_obj"].id
            for e in candidats
            if e["ouvrage_obj"].id in ctx.ouvrage_ids
        ]
        if not cibles:
            oid = _ouvrage_depuis_libelle(row.get("description") or "", index_noms)
            if oid:
                cibles = [oid]
        cibles = [oid for oid in cibles if _ouvrage_sous_gestion_a(ctx, oid, ref_date)]
        if not cibles:
            non_affecte += montant
            continue
        part = montant / len(cibles)
        for oid in cibles:
            par_ouvrage[oid] += part
    return dict(par_ouvrage), non_affecte


def depenses_pieces_planning(ctx: ContexteAnalyse):
    par_ouvrage = defaultdict(lambda: D0)
    non_affecte = D0

    rows = list(
        PlanningDetail.objects.filter(
            montant__gt=0,
            designation__type_avance_caissiere__iexact=TYPE_AVANCE_BON_LIVRAISON,
        )
        .filter(
            planning__date__date__gte=ctx.date_debut - relativedelta(days=2),
            planning__date__date__lte=ctx.date_fin + relativedelta(days=2),
        )
        .select_related("planning", "point_eau", "designation")
        .values(
            "montant",
            "planning__date",
            "planning__ouvrage_id",
            "point_eau__ouvrage_id",
            "designation__nom",
        )
    )
    for row in rows:
        local = _to_local_date(row["planning__date"])
        if not local or not (ctx.date_debut <= local <= ctx.date_fin):
            continue
        nom_designation = (row.get("designation__nom") or "").lower()
        if "forfaitaire" in nom_designation or "recette" in nom_designation:
            continue
        montant = Decimal(str(row["montant"] or 0))
        if montant <= 0:
            continue
        ouvrage_id = row.get("planning__ouvrage_id") or row.get("point_eau__ouvrage_id")
        if ouvrage_id not in ctx.ouvrage_ids:
            non_affecte += montant
            continue
        modalite = ctx.modalite_by_ouvrage.get(ouvrage_id)
        if modalite and modalite.date_debut and local < modalite.date_debut:
            # dépense antérieure au début de gestion => construction, on ignore
            continue
        par_ouvrage[ouvrage_id] += montant
    return dict(par_ouvrage), non_affecte


# --------------------------------------------------------------------------- #
# Recettes                                                                    #
# --------------------------------------------------------------------------- #
def _nb_trimestres_periode(modalite, d1: date, d2: date) -> int:
    """Nombre de trimestres calendaires entièrement/partiellement couverts par [d1, d2]
    après le début de gestion de la modalité (approximation)."""
    debut = d1
    if modalite and modalite.date_debut and modalite.date_debut > debut:
        debut = modalite.date_debut
    if debut > d2:
        return 0
    mois = (d2.year - debut.year) * 12 + (d2.month - debut.month) + 1
    return max(0, round(mois / 3))


def recettes_ouvrages(ctx: ContexteAnalyse):
    realise = defaultdict(lambda: D0)
    prevu = defaultdict(lambda: D0)

    # --- Réalisé : DiameX 707401 + 748411 (fenêtre recettes : mois en cours ET dernier
    #     mois complet exclus, cf. _date_fin_recettes) --- #
    rows = (
        _diamex_periode_recettes(
            ctx,
            BaseDiameX.objects.filter(
                compte_code__in=[COMPTE_RECETTE_VOLUME, COMPTE_RECETTE_FORFAIT],
                montant_in__gt=0,
            ),
        ).values("montant_in", "description", "compte_code", "date_rec", "date_m")
    )
    for row in rows:
        montant = Decimal(str(row["montant_in"] or 0))
        if montant <= 0:
            continue
        ref_date = row.get("date_rec") or row.get("date_m")
        extraction = extraire_ouvrage_et_mois_generique(
            row.get("description") or "", row.get("compte_code") or ""
        )
        if isinstance(extraction, list):
            candidats = [e for e in extraction if e and e.get("ouvrage_obj")]
        else:
            candidats = [extraction] if extraction and extraction.get("ouvrage_obj") else []
        cibles = [
            e["ouvrage_obj"].id
            for e in candidats
            if e["ouvrage_obj"].id in ctx.ouvrage_ids
            and _ouvrage_sous_gestion_a(ctx, e["ouvrage_obj"].id, ref_date)
        ]
        if not cibles:
            continue
        part = montant / len(cibles)
        for oid in cibles:
            realise[oid] += part

    # --- Prévu volume : montants de relevés dans la fenêtre recettes, après début de
    #     gestion (mois en cours ET dernier mois complet exclus) --- #
    releve_rows = (
        Releve.objects.filter(
            point_eau__ouvrage_id__in=ctx.ouvrage_ids,
            montant__isnull=False,
            datereleve__gte=ctx.date_debut,
            datereleve__lte=ctx.date_fin_recettes,
        ).values("point_eau__ouvrage_id", "montant", "datereleve")
    )
    for row in releve_rows:
        oid = row["point_eau__ouvrage_id"]
        if not _ouvrage_sous_gestion_a(ctx, oid, row["datereleve"]):
            continue
        prevu[oid] += Decimal(str(row["montant"] or 0))

    # --- Prévu forfait : tarif forfaitaire x nb trimestres --- #
    forfait_pe = (
        PointEau.objects.filter(
            ouvrage_id__in=ctx.ouvrage_ids,
            tarifforfaitaire__isnull=False,
            tarifforfaitaire__gt=0,
        )
        .exclude(type_point_eau__nom_type__icontains="privé")
        .exclude(type_point_eau__nom_type__iexact="bp")
        .values("ouvrage_id", "tarifforfaitaire", "pourcentage_tarif", "type_point_eau_id")
    )
    annee_tarif = (ctx.date_fin_recettes or ctx.date_fin).year  # tarif en vigueur cette année-là
    tarif_par_ouvrage = defaultdict(lambda: D0)
    for row in forfait_pe:
        tarif_par_ouvrage[row["ouvrage_id"]] += tarif_depuis_valeurs(
            row["type_point_eau_id"], row["pourcentage_tarif"], row["tarifforfaitaire"], annee_tarif
        )
    for oid, tarif_total in tarif_par_ouvrage.items():
        modalite = ctx.modalite_by_ouvrage.get(oid)
        if modalite and modalite.modalitepaiement not in MODALITES_FORFAIT:
            continue
        nb_t = _nb_trimestres_periode(modalite, ctx.date_debut, ctx.date_fin_recettes)
        prevu[oid] += tarif_total * nb_t

    return dict(realise), dict(prevu)


# --------------------------------------------------------------------------- #
# Indicateurs financiers (recouvrement, charges, impayés, criticité)          #
# --------------------------------------------------------------------------- #
def _rang_percentile(paires: list) -> dict:
    """Rang-percentile [0, 1] d'une liste de (clé, valeur) : 0 = la plus petite valeur du
    lot, 1 = la plus grande. Les ex-aequo se voient attribuer le même rang moyen. Choisi
    plutôt qu'un min-max brut car un ouvrage isolé avec une valeur extrême (ex. ratio de
    charges très élevé) ne doit pas écraser l'échelle et rendre tous les autres ouvrages
    artificiellement "sains" par comparaison — seul l'ORDRE compte ici, pas l'écart brut.
    Une seule valeur -> rang neutre 0.5 (rien à comparer)."""
    n = len(paires)
    if n == 0:
        return {}
    if n == 1:
        return {paires[0][0]: 0.5}
    ordonnes = sorted(paires, key=lambda item: item[1])
    rangs = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordonnes[j + 1][1] == ordonnes[i][1]:
            j += 1
        rang_moyen = (i + j) / 2
        for k in range(i, j + 1):
            rangs[ordonnes[k][0]] = rang_moyen
        i = j + 1
    return {cle: rang / (n - 1) for cle, rang in rangs.items()}


def calculer_indicateurs_financiers(lignes: list) -> None:
    """Ajoute in-place, à chaque ligne de `lignes` (dict comportant déjà les clés
    ``depenses.total``, ``recette_realisee`` et ``recette_prevue`` — qu'il s'agisse d'un
    ouvrage ou d'une commune, peu importe), les indicateurs de recouvrement / criticité :

    - ``recettes_facturees``   : alias de ``recette_prevue`` (déjà calculée ailleurs —
      relevés + tarif forfaitaire estimé), c.-à-d. ce qui aurait dû être payé sur la
      période ;
    - ``impayes``               = max(recettes_facturees − recettes_encaissees, 0) ;
    - ``taux_recouvrement``     = recettes_encaissees / recettes_facturees (en %),
      ``None`` si recettes_facturees == 0 (aucune base de facturation connue) ;
    - ``ratio_charges``         = dépenses / recettes_encaissees (>1 = ouvrage
      déficitaire en trésorerie réelle) ; ``0`` si dépenses == 0 (aucune charge = pas de
      problème sur cet axe, quel que soit l'état des recettes) ; si dépenses > 0 et
      recettes encaissées == 0, le ratio est mathématiquement infini
      (``ratio_charges = None``, ``ratio_charges_infini = True``) ;
    - ``taux_impayes``          = impayes / recettes_facturees (en %), ``0`` si
      recettes_facturees == 0 (impayes est alors nécessairement 0 aussi) ;
    - ``sans_historique``       = True si dépenses, recette réalisée ET recette facturée
      sont TOUTES nulles (ouvrage/commune jamais mouvementé sur la période — rien à
      évaluer) : ces lignes sont exclues du calcul de score (indicateurs à ``None``) ;
    - ``score_criticite``       = 100 × (0.6 × rang-percentile(ratio_charges) +
      0.4 × rang-percentile(taux_impayes)), calculé UNIQUEMENT parmi les lignes du
      résultat courant (donc relatif aux filtres actifs, pas absolu). Les ratios
      "infinis" reçoivent le rang maximal (1.0), le plus critique. ``None`` si
      ``sans_historique``.
    """
    ratio_pool = []    # (index, ratio_charges) — valeur None => "infini" (traité à part)
    impayes_pool = []  # (index, taux_impayes en fraction 0..1)

    for i, ligne in enumerate(lignes):
        depense_totale = Decimal(str(ligne["depenses"]["total"]))
        rec_reel = Decimal(str(ligne["recette_realisee"]))
        rec_facturee = Decimal(str(ligne["recette_prevue"]))

        sans_historique = depense_totale == D0 and rec_reel == D0 and rec_facturee == D0
        ligne["recettes_facturees"] = float(rec_facturee)
        ligne["sans_historique"] = sans_historique

        if sans_historique:
            ligne["impayes"] = 0.0
            ligne["taux_recouvrement"] = None
            ligne["ratio_charges"] = None
            ligne["ratio_charges_infini"] = False
            ligne["taux_impayes"] = None
            ligne["score_criticite"] = None
            continue

        impayes = max(rec_facturee - rec_reel, D0)
        taux_recouvrement = (rec_reel / rec_facturee) if rec_facturee > D0 else None
        taux_impayes = (impayes / rec_facturee) if rec_facturee > D0 else D0

        if depense_totale == D0:
            ratio_charges, ratio_infini = D0, False
        elif rec_reel > D0:
            ratio_charges, ratio_infini = depense_totale / rec_reel, False
        else:
            ratio_charges, ratio_infini = None, True

        ligne["impayes"] = float(impayes)
        ligne["taux_recouvrement"] = (
            round(float(taux_recouvrement) * 100, 1) if taux_recouvrement is not None else None
        )
        ligne["ratio_charges"] = float(ratio_charges) if ratio_charges is not None else None
        ligne["ratio_charges_infini"] = ratio_infini
        ligne["taux_impayes"] = round(float(taux_impayes) * 100, 1)

        ratio_pool.append((i, None if ratio_infini else float(ratio_charges)))
        impayes_pool.append((i, float(taux_impayes)))

    rangs_ratio = _rang_percentile([(i, v) for i, v in ratio_pool if v is not None])
    for i, v in ratio_pool:
        if v is None:
            rangs_ratio[i] = 1.0  # ratio "infini" : toujours le plus critique du lot
    rangs_impayes = _rang_percentile(impayes_pool)

    for i, ligne in enumerate(lignes):
        if ligne["sans_historique"]:
            continue
        r_ratio = rangs_ratio.get(i, 0.5)
        r_impayes = rangs_impayes.get(i, 0.5)
        score = 100 * (
            float(POIDS_SCORE_RATIO_CHARGES) * r_ratio
            + float(POIDS_SCORE_TAUX_IMPAYES) * r_impayes
        )
        ligne["score_criticite"] = round(score, 1)


def _cle_tri_criticite(ligne: dict):
    """Tri décroissant par score de criticité (ouvrage le plus « maivoas » en premier),
    les lignes ``sans_historique`` (score ``None``) toujours reléguées en fin de liste."""
    score = ligne.get("score_criticite")
    return (score is None, -(score or 0))


# --------------------------------------------------------------------------- #
# Assemblage                                                                  #
# --------------------------------------------------------------------------- #
def construire_analyse(params: ParamsAnalyse, reference: date | None = None) -> dict:
    d1, d2 = resoudre_periode(reference)
    ctx = charger_contexte(d1, d2, params.base_id, params.region_id, params.district_id, params.commune_id)

    if params.inc_salaires:
        dep_sal_d, dep_sal_h, na_salaires = depenses_salaires_charges(ctx, params.alpha)
        if not params.inc_salaires_hierarchie:
            dep_sal_h = {}
    else:
        dep_sal_d, dep_sal_h, na_salaires = {}, {}, D0

    if params.inc_vehicules:
        dep_veh_d, dep_veh_h, na_vehicules = depenses_vehicules(ctx, params.alpha)
        if not params.inc_vehicules_hierarchie:
            dep_veh_h = {}
    else:
        dep_veh_d, dep_veh_h, na_vehicules = {}, {}, D0

    dep_direct, na_direct = (
        depenses_ouvrage_direct(ctx) if params.inc_ouvrage_direct else ({}, D0)
    )
    dep_pieces, na_pieces = (
        depenses_pieces_planning(ctx) if params.inc_pieces else ({}, D0)
    )
    realise, prevu = recettes_ouvrages(ctx)

    non_affecte_total = na_salaires + na_vehicules + na_direct + na_pieces
    repartition_globale = poids_ouvrages(ctx, params.alpha) if params.repartir_non_affecte else {}

    lignes = []
    for oid in ctx.ouvrage_ids:
        ouvrage = ctx.ouvrages_by_id.get(oid)
        d_sal_d = dep_sal_d.get(oid, D0)
        d_sal_h = dep_sal_h.get(oid, D0)
        d_veh_d = dep_veh_d.get(oid, D0)
        d_veh_h = dep_veh_h.get(oid, D0)
        d_dir = dep_direct.get(oid, D0)
        d_pie = dep_pieces.get(oid, D0)
        if params.repartir_non_affecte and repartition_globale:
            poids = repartition_globale.get(oid, D0)
            d_sal_d += na_salaires * poids
            d_veh_d += na_vehicules * poids
            d_dir += na_direct * poids
            d_pie += na_pieces * poids
        depense_totale = d_sal_d + d_sal_h + d_veh_d + d_veh_h + d_dir + d_pie
        rec_reel = realise.get(oid, D0)
        rec_prev = prevu.get(oid, D0)
        marge = rec_reel - depense_totale
        ecart_recette = rec_reel - rec_prev
        penibilite_pct = (
            float((ecart_recette / rec_prev) * 100) if rec_prev else None
        )
        commune_id_oid = ctx.commune_by_ouvrage.get(oid)
        district_id_oid = ctx.district_by_ouvrage.get(oid)
        region_id_oid = ctx.region_by_ouvrage.get(oid)
        lignes.append(
            {
                "ouvrage_id": str(oid),
                "ouvrage_nom": getattr(ouvrage, "nom_ouvrage", "?"),
                "commune_id": str(commune_id_oid) if commune_id_oid else "",
                "commune_nom": ctx.commune_nom_by_id.get(commune_id_oid) or "Sans commune",
                "district_id": str(district_id_oid) if district_id_oid else "",
                "district_nom": ctx.district_nom_by_id.get(district_id_oid) or "Sans district",
                "region_id": str(region_id_oid) if region_id_oid else "",
                "region_nom": ctx.region_nom_by_id.get(region_id_oid) or "Sans région",
                "pe_public": ctx.pe_public_by_ouvrage.get(oid, 0),
                "jours_planning": ctx.jours_planning_by_ouvrage.get(oid, 0),
                "depenses": {
                    "salaires_direct": float(d_sal_d),
                    "salaires_hierarchie": float(d_sal_h),
                    "vehicules_direct": float(d_veh_d),
                    "vehicules_hierarchie": float(d_veh_h),
                    "ouvrage_direct": float(d_dir),
                    "pieces_planning": float(d_pie),
                    "total": float(depense_totale),
                },
                "recette_realisee": float(rec_reel),
                "recette_prevue": float(rec_prev),
                "marge": float(marge),
                "ecart_recette": float(ecart_recette),
                "penibilite_pct": penibilite_pct,
            }
        )

    calculer_indicateurs_financiers(lignes)
    lignes.sort(key=_cle_tri_criticite)

    return {
        "periode": {"debut": d1.isoformat(), "fin": d2.isoformat()},
        "periode_recettes": {"debut": d1.isoformat(), "fin": ctx.date_fin_recettes.isoformat()},
        "base_id": ctx.base_id,
        "base_volet": ctx.base_volet,
        "region_id": ctx.filtre_region_id,
        "district_id": ctx.filtre_district_id,
        "commune_id": ctx.filtre_commune_id,
        "params": {
            "alpha": float(params.alpha),
            "inc_salaires": params.inc_salaires,
            "inc_salaires_hierarchie": params.inc_salaires_hierarchie,
            "inc_vehicules": params.inc_vehicules,
            "inc_vehicules_hierarchie": params.inc_vehicules_hierarchie,
            "inc_ouvrage_direct": params.inc_ouvrage_direct,
            "inc_pieces": params.inc_pieces,
            "repartir_non_affecte": params.repartir_non_affecte,
            "base_id": ctx.base_id,
            "region_id": ctx.filtre_region_id,
            "district_id": ctx.filtre_district_id,
            "commune_id": ctx.filtre_commune_id,
        },
        "lignes": lignes,
        "non_affecte": {
            "salaires": float(na_salaires),
            "vehicules": float(na_vehicules),
            "ouvrage_direct": float(na_direct),
            "pieces_planning": float(na_pieces),
            "total": float(non_affecte_total),
            "reparti": params.repartir_non_affecte,
        },
        "totaux": {
            "depenses": float(sum(Decimal(str(l["depenses"]["total"])) for l in lignes)),
            "recette_realisee": float(sum(Decimal(str(l["recette_realisee"])) for l in lignes)),
            "recette_prevue": float(sum(Decimal(str(l["recette_prevue"])) for l in lignes)),
            "nb_ouvrages": len(lignes),
        },
    }


DEP_KEYS_AGREGATION = (
    "salaires_direct", "salaires_hierarchie", "vehicules_direct",
    "vehicules_hierarchie", "ouvrage_direct", "pieces_planning", "total",
)


def construire_analyse_communes(params: ParamsAnalyse, reference: date | None = None) -> dict:
    """Même analyse que `construire_analyse`, agrégée par commune (pour comparer les
    communes entre elles plutôt que les ouvrages). Réutilise construire_analyse() tel
    quel (mêmes filtres base/région/district/commune, même modélisation) puis regroupe
    ses lignes ouvrage par commune."""
    analyse = construire_analyse(params, reference)

    groupes: dict = {}
    for l in analyse["lignes"]:
        cle = l["commune_id"] or l["commune_nom"]
        g = groupes.setdefault(cle, {
            "commune_id": l["commune_id"],
            "commune_nom": l["commune_nom"],
            "district_id": l["district_id"],
            "district_nom": l["district_nom"],
            "region_id": l["region_id"],
            "region_nom": l["region_nom"],
            "nb_ouvrages": 0,
            "pe_public": 0,
            "jours_planning": 0,
            "depenses": {k: 0.0 for k in DEP_KEYS_AGREGATION},
            "recette_realisee": 0.0,
            "recette_prevue": 0.0,
        })
        g["nb_ouvrages"] += 1
        g["pe_public"] += l["pe_public"]
        g["jours_planning"] += l["jours_planning"]
        for k in DEP_KEYS_AGREGATION:
            g["depenses"][k] += l["depenses"][k]
        g["recette_realisee"] += l["recette_realisee"]
        g["recette_prevue"] += l["recette_prevue"]

    lignes_commune = []
    for g in groupes.values():
        marge = g["recette_realisee"] - g["depenses"]["total"]
        ecart_recette = g["recette_realisee"] - g["recette_prevue"]
        penibilite_pct = (ecart_recette / g["recette_prevue"] * 100) if g["recette_prevue"] else None
        lignes_commune.append({
            **g,
            "marge": marge,
            "ecart_recette": ecart_recette,
            "penibilite_pct": penibilite_pct,
        })
    # Indicateurs de recouvrement / criticité recalculés au niveau commune : les ratios ne
    # sont pas additifs (on ne peut pas moyenner des ratios d'ouvrages), donc on les
    # recalcule sur les montants déjà agrégés ci-dessus plutôt que d'agréger les scores
    # par ouvrage.
    calculer_indicateurs_financiers(lignes_commune)
    lignes_commune.sort(key=_cle_tri_criticite)

    analyse["lignes_communes"] = lignes_commune
    analyse["totaux_communes"] = {
        "depenses": sum(l["depenses"]["total"] for l in lignes_commune),
        "recette_realisee": sum(l["recette_realisee"] for l in lignes_commune),
        "recette_prevue": sum(l["recette_prevue"] for l in lignes_commune),
        "nb_communes": len(lignes_commune),
    }
    del analyse["lignes"]
    return analyse


# --------------------------------------------------------------------------- #
# Détail (drill-down d'une cellule)                                           #
# --------------------------------------------------------------------------- #
CATEGORIES_DETAIL = {
    "salaires_direct": "Salaires / charges — responsable direct",
    "salaires_hierarchie": "Salaires / charges — via la hiérarchie",
    "vehicules_direct": "Véhicules — conducteur responsable direct",
    "vehicules_hierarchie": "Véhicules — conducteur via la hiérarchie",
    "ouvrage_direct": "Dépenses ouvrage (nom dans le libellé)",
    "pieces_planning": "Pièces / achats du planning",
    "recette_realisee": "Recette réalisée (DiameX)",
    "recette_prevue": "Recette prévue (approximation)",
}

# Règle transverse rappelée dans chaque méthode
_NOTE_GESTION = (
    " Pour chaque ouvrage, seules les lignes datées à partir de son début de gestion par "
    "Soakoja (date_debut de la modalité) sont retenues."
)

METHODES_DETAIL = {
    "salaires_direct": (
        "Lignes DiameX sur comptes « Compte employé » (montant_out). Chaque ligne est "
        "rattachée à l'employé via son surnom (colonne Detail/Pers), puis ventilée sur les "
        "ouvrages dont il est FORMELLEMENT responsable (responsabilité datée EmployeOuvrages "
        "ou modalité de gestion à son nom — la présence au planning ne suffit pas), au prorata "
        "α·(jours de planning) + (1−α)·(points d'eau publics hors BP). "
        "Cas particulier : compte 621101, libellé contenant « Prestation MI » (Mpikojakoja "
        "ifotony) → réparti uniquement sur les ouvrages « Responsables ouvrages » (EmployeOuvrages) "
        "de l'employé, au prorata des points d'eau publics ; si un de ces ouvrages est le chef-lieu "
        "de sa commune (même nom, sauf Vohilengo AEPG), sa part est en outre répartie sur tous les "
        "ouvrages de la commune (même prorata)."
    ),
    "salaires_hierarchie": (
        "Idem « responsable direct », mais pour les employés sans aucun ouvrage formel : le "
        "coût redescend sur les ouvrages formellement rattachés à leurs subordonnés."
    ),
    "vehicules_direct": (
        "Lignes DiameX carburant (606100/606107) et comptes « Compte véhicule ». Rattachées "
        "au véhicule par la plaque (Detail/Description/Info), puis au conducteur via "
        "l'affectation active à la date, puis ventilées comme les salaires."
    ),
    "vehicules_hierarchie": "Idem véhicules, conducteur rattaché via la hiérarchie.",
    "ouvrage_direct": (
        "Lignes DiameX sur comptes « Nécessite ouvrage » ou « Compte à répartir sur un "
        "ouvrage » : le nom de l'ouvrage est extrait du libellé ; montant affecté à 100 % "
        "(réparti si plusieurs ouvrages cités)."
    ),
    "pieces_planning": (
        "Lignes PlanningDetail (montant > 0) de désignation « Bon de livraison » (type "
        "avance caissière) rattachées à l'ouvrage du planning. Exclues : désignations "
        "« Avance » (Prestation MI, Essence, Loyer, Repas — déjà comptées via DiameX), "
        "recette, et lignes antérieures au début de gestion de l'ouvrage."
    ),
    "recette_realisee": "Lignes DiameX 707401 (volume) + 748411 (forfait), ouvrage extrait du libellé.",
    "recette_prevue": (
        "Volume : somme des montants des relevés dans la fenêtre. Forfait : Σ tarif "
        "forfaitaire des points d'eau non-BP × nombre de trimestres de gestion."
    ),
}

# Recettes : en plus du mois en cours, le dernier mois complet est aussi exclu (paiements
# et relevés souvent encore incomplets à cette date) — fenêtre 1 mois plus courte que les
# dépenses. Cf. _date_fin_recettes / ContexteAnalyse.date_fin_recettes.
_NOTE_RECETTES_FENETRE = (
    " Fenêtre recettes : le mois en cours ET le dernier mois complet sont exclus (les "
    "paiements/relevés de ce dernier mois arrivent souvent encore en retard) — la fenêtre "
    "s'arrête donc un mois plus tôt que celle des dépenses."
)
METHODES_DETAIL["recette_realisee"] += _NOTE_RECETTES_FENETRE
METHODES_DETAIL["recette_prevue"] += _NOTE_RECETTES_FENETRE

for _k in ("salaires_direct", "salaires_hierarchie", "vehicules_direct", "vehicules_hierarchie",
           "ouvrage_direct", "recette_realisee", "recette_prevue"):
    METHODES_DETAIL[_k] += _NOTE_GESTION


def _fmt_date(value) -> str:
    d = _to_local_date(value)
    return d.isoformat() if d else ""


def _detail_salaires(ctx, oid, alpha, variante):
    lignes = []
    total = D0
    rows = (
        _diamex_periode(
            ctx,
            BaseDiameX.objects.filter(compte__employe_obligatoire=True, montant_out__gt=0),
        )
        .select_related("compte")
        .values(
            "id_access", "date_rec", "date_m", "montant_out", "description", "detail", "pers",
            "compte_code", "compte__nom_compte",
        )
    )
    for row in rows:
        montant = Decimal(str(row["montant_out"] or 0))
        if montant <= 0:
            continue
        cle = (row.get("detail") or row.get("pers") or "").strip().lower()
        employe = ctx.employe_by_surnom.get(cle)
        if not employe:
            continue
        ref_date = row.get("date_rec") or row.get("date_m")
        compte_code = row.get("compte_code") or ""
        compte_nom = row.get("compte__nom_compte") or ""

        if _est_prestation_mi(row.get("compte_code"), row.get("description")):
            if variante != "direct":
                continue
            ventilation = repartir_prestation_mi(ctx, montant, employe.id)
            if oid not in ventilation:
                continue
            impute = ventilation[oid]
            total += impute
            note = f"{employe.nom_affichage} · Prestation MI"
            directs = ctx.employe_ouvrages_by_emp.get(employe.id, set()) & ctx.ouvrage_ids
            chef_lieux = [o for o in directs if _est_chef_lieu(ctx, o)]
            if chef_lieux and oid not in directs:
                note += f" (via chef-lieu {ctx.ouvrages_by_id.get(chef_lieux[0]).nom_ouvrage})"
            elif oid in chef_lieux:
                note += " (chef-lieu, réparti sur la commune)"
            lignes.append({
                "date": _fmt_date(ref_date),
                "reference": f"DiameX #{row.get('id_access')}",
                "compte_code": compte_code,
                "compte_nom": compte_nom,
                "libelle": row.get("description") or "",
                "montant_brut": float(montant),
                "facteur": float(impute / montant) if montant else 0.0,
                "montant_impute": float(impute),
                "note": note,
            })
            continue

        ventilation, mode = repartir_cout_employe(ctx, montant, employe.id, alpha, ref_date)
        if mode != variante or oid not in ventilation:
            continue
        impute = ventilation[oid]
        total += impute
        lignes.append({
            "date": _fmt_date(row.get("date_rec") or row.get("date_m")),
            "reference": f"DiameX #{row.get('id_access')}",
            "compte_code": compte_code,
            "compte_nom": compte_nom,
            "libelle": row.get("description") or "",
            "montant_brut": float(montant),
            "facteur": float(impute / montant) if montant else 0.0,
            "montant_impute": float(impute),
            "note": f"{employe.nom_affichage} · {mode}",
        })
    lignes.sort(key=lambda x: x["montant_impute"], reverse=True)
    return total, lignes


def _detail_vehicules(ctx, oid, alpha, variante):
    from django.db.models import Q
    from apps.inventory.models_vehicles import AffectationVehicule, Vehicule

    lignes = []
    total = D0
    vehicules = list(Vehicule.objects.all().values("id", "immatriculation"))
    plate_index = sorted(
        ((v["id"], v["immatriculation"], _normalize_plate(v["immatriculation"])) for v in vehicules if v["immatriculation"]),
        key=lambda item: len(item[2]),
        reverse=True,
    )
    aff_by_vehicule = defaultdict(list)
    for aff in AffectationVehicule.objects.all().values("vehicule_id", "employe_id", "date_debut", "date_fin"):
        aff_by_vehicule[aff["vehicule_id"]].append(aff)

    rows = (
        _diamex_periode(
            ctx,
            BaseDiameX.objects.filter(montant_out__gt=0).filter(
                Q(compte__compte_vehicule=True) | Q(compte_code__in=COMPTES_CARBURANT)
            ),
        )
        .select_related("compte")
        .values(
            "id_access", "date_rec", "date_m", "montant_out", "description", "detail", "info",
            "compte_code", "compte__nom_compte",
        )
    )
    for row in rows:
        montant = Decimal(str(row["montant_out"] or 0))
        if montant <= 0:
            continue
        texte = _normalize_plate(f"{row.get('detail') or ''} {row.get('description') or ''} {row.get('info') or ''}")
        match = next(((vid, imm) for vid, imm, plate in plate_index if plate and plate in texte), None)
        if not match:
            continue
        vehicule_id, immat = match
        ref_date = row.get("date_rec") or row.get("date_m")
        conducteur_id = None
        for aff in aff_by_vehicule.get(vehicule_id, []):
            debut, fin = aff["date_debut"], aff["date_fin"]
            if debut and ref_date and debut <= ref_date and (fin is None or fin >= ref_date):
                conducteur_id = aff["employe_id"]
                break
        if not conducteur_id or conducteur_id not in ctx.employe_ids_scope:
            continue
        ventilation, mode = repartir_cout_employe(ctx, montant, conducteur_id, alpha, ref_date)
        if mode != variante or oid not in ventilation:
            continue
        impute = ventilation[oid]
        total += impute
        conducteur = Employe.objects.filter(id=conducteur_id).first()
        lignes.append({
            "date": _fmt_date(ref_date),
            "reference": f"DiameX #{row.get('id_access')}",
            "compte_code": row.get("compte_code") or "",
            "compte_nom": row.get("compte__nom_compte") or "",
            "libelle": row.get("description") or "",
            "montant_brut": float(montant),
            "facteur": float(impute / montant) if montant else 0.0,
            "montant_impute": float(impute),
            "note": f"{immat} · {conducteur.nom_affichage if conducteur else '?'} · {mode}",
        })
    lignes.sort(key=lambda x: x["montant_impute"], reverse=True)
    return total, lignes


def _detail_ouvrage_direct(ctx, oid):
    from django.db.models import Q

    index_noms = _index_noms_ouvrages(ctx)
    lignes = []
    total = D0
    rows = (
        _diamex_periode(
            ctx,
            BaseDiameX.objects.filter(montant_out__gt=0)
            .filter(Q(compte__necessite_ouvrage=True) | Q(compte__compte_ouvrage_analyse=True))
            .exclude(compte__employe_obligatoire=True)
            .exclude(compte__compte_vehicule=True),
        )
        .select_related("compte")
        .values("id_access", "date_rec", "date_m", "montant_out", "description", "compte_code", "compte__nom_compte")
    )
    for row in rows:
        montant = Decimal(str(row["montant_out"] or 0))
        if montant <= 0:
            continue
        ref_date = row.get("date_rec") or row.get("date_m")
        extraction = extraire_ouvrage_et_mois_generique(row.get("description") or "", row.get("compte_code") or "")
        if isinstance(extraction, list):
            candidats = [e for e in extraction if e and e.get("ouvrage_obj")]
        else:
            candidats = [extraction] if extraction and extraction.get("ouvrage_obj") else []
        cibles = [e["ouvrage_obj"].id for e in candidats if e["ouvrage_obj"].id in ctx.ouvrage_ids]
        methode = "extrait du libellé"
        if not cibles:
            fallback = _ouvrage_depuis_libelle(row.get("description") or "", index_noms)
            if fallback:
                cibles = [fallback]
                methode = "nom d'ouvrage reconnu dans le libellé"
        cibles = [c for c in cibles if _ouvrage_sous_gestion_a(ctx, c, ref_date)]
        if oid not in cibles:
            continue
        impute = montant / len(cibles)
        total += impute
        lignes.append({
            "date": _fmt_date(row.get("date_rec") or row.get("date_m")),
            "reference": f"DiameX #{row.get('id_access')}",
            "compte_code": row.get("compte_code") or "",
            "compte_nom": row.get("compte__nom_compte") or "",
            "libelle": row.get("description") or "",
            "montant_brut": float(montant),
            "facteur": float(impute / montant) if montant else 0.0,
            "montant_impute": float(impute),
            "note": methode + (f" · {len(cibles)} ouvrages" if len(cibles) > 1 else ""),
        })
    lignes.sort(key=lambda x: x["montant_impute"], reverse=True)
    return total, lignes


def _detail_pieces(ctx, oid):
    lignes = []
    total = D0
    rows = list(
        PlanningDetail.objects.filter(
            montant__gt=0,
            designation__type_avance_caissiere__iexact=TYPE_AVANCE_BON_LIVRAISON,
        )
        .filter(
            planning__date__date__gte=ctx.date_debut - relativedelta(days=2),
            planning__date__date__lte=ctx.date_fin + relativedelta(days=2),
        )
        .filter(Q_ouvrage_pieces(oid))
        .select_related("planning", "designation", "compte")
        .values("montant", "planning__date", "designation__nom", "acheteur", "compte__compte", "compte__nom_compte")
    )
    modalite = ctx.modalite_by_ouvrage.get(oid)
    for row in rows:
        local = _to_local_date(row["planning__date"])
        if not local or not (ctx.date_debut <= local <= ctx.date_fin):
            continue
        nom_designation = (row.get("designation__nom") or "").lower()
        if "forfaitaire" in nom_designation or "recette" in nom_designation:
            continue
        if modalite and modalite.date_debut and local < modalite.date_debut:
            continue
        montant = Decimal(str(row["montant"] or 0))
        if montant <= 0:
            continue
        total += montant
        lignes.append({
            "date": local.isoformat(),
            "reference": "Bon de livraison",
            "compte_code": row.get("compte__compte") or "",
            "compte_nom": row.get("compte__nom_compte") or "",
            "libelle": row.get("designation__nom") or "",
            "montant_brut": float(montant),
            "facteur": 1.0,
            "montant_impute": float(montant),
            "note": f"acheteur : {row.get('acheteur') or '—'}",
        })
    lignes.sort(key=lambda x: x["montant_impute"], reverse=True)
    return total, lignes


def Q_ouvrage_pieces(oid):
    from django.db.models import Q

    return Q(planning__ouvrage_id=oid) | Q(point_eau__ouvrage_id=oid)


def _detail_recette_realisee(ctx, oid):
    lignes = []
    total = D0
    rows = (
        _diamex_periode_recettes(
            ctx,
            BaseDiameX.objects.filter(
                compte_code__in=[COMPTE_RECETTE_VOLUME, COMPTE_RECETTE_FORFAIT], montant_in__gt=0
            ),
        )
        .select_related("compte")
        .values("id_access", "date_rec", "date_m", "montant_in", "description", "compte_code", "compte__nom_compte")
    )
    for row in rows:
        montant = Decimal(str(row["montant_in"] or 0))
        if montant <= 0:
            continue
        ref_date = row.get("date_rec") or row.get("date_m")
        extraction = extraire_ouvrage_et_mois_generique(row.get("description") or "", row.get("compte_code") or "")
        if isinstance(extraction, list):
            candidats = [e for e in extraction if e and e.get("ouvrage_obj")]
        else:
            candidats = [extraction] if extraction and extraction.get("ouvrage_obj") else []
        cibles = [
            e["ouvrage_obj"].id
            for e in candidats
            if e["ouvrage_obj"].id in ctx.ouvrage_ids
            and _ouvrage_sous_gestion_a(ctx, e["ouvrage_obj"].id, ref_date)
        ]
        if oid not in cibles:
            continue
        impute = montant / len(cibles)
        total += impute
        lignes.append({
            "date": _fmt_date(ref_date),
            "reference": f"DiameX #{row.get('id_access')}",
            "compte_code": row.get("compte_code") or "",
            "compte_nom": row.get("compte__nom_compte") or "",
            "libelle": row.get("description") or "",
            "montant_brut": float(montant),
            "facteur": float(impute / montant) if montant else 0.0,
            "montant_impute": float(impute),
            "note": "",
        })
    lignes.sort(key=lambda x: x["montant_impute"], reverse=True)
    return total, lignes


def _detail_recette_prevue(ctx, oid):
    lignes = []
    total = D0
    releve_rows = (
        Releve.objects.filter(
            point_eau__ouvrage_id=oid,
            montant__isnull=False,
            datereleve__gte=ctx.date_debut,
            datereleve__lte=ctx.date_fin_recettes,
        ).select_related("point_eau").values("datereleve", "montant", "point_eau__code_point_eau", "abonne")
    )
    for row in releve_rows:
        montant = Decimal(str(row["montant"] or 0))
        if montant <= 0:
            continue
        if not _ouvrage_sous_gestion_a(ctx, oid, row["datereleve"]):
            continue
        total += montant
        lignes.append({
            "date": row["datereleve"].isoformat() if row["datereleve"] else "",
            "reference": "Relevé",
            "compte_code": "",
            "compte_nom": "",
            "libelle": f"{row.get('point_eau__code_point_eau') or ''} · {row.get('abonne') or ''}".strip(" ·"),
            "montant_brut": float(montant),
            "facteur": 1.0,
            "montant_impute": float(montant),
            "note": "montant facturé du relevé",
        })

    modalite = ctx.modalite_by_ouvrage.get(oid)
    if not (modalite and modalite.modalitepaiement not in MODALITES_FORFAIT):
        nb_t = _nb_trimestres_periode(modalite, ctx.date_debut, ctx.date_fin_recettes)
        forfait_pe = (
            PointEau.objects.filter(
                ouvrage_id=oid, tarifforfaitaire__isnull=False, tarifforfaitaire__gt=0
            )
            .exclude(type_point_eau__nom_type__icontains="privé")
            .exclude(type_point_eau__nom_type__iexact="bp")
            .values("code_point_eau", "tarifforfaitaire", "pourcentage_tarif", "type_point_eau_id")
        )
        annee_tarif = (ctx.date_fin_recettes or ctx.date_fin).year
        for row in forfait_pe:
            tarif = tarif_depuis_valeurs(
                row["type_point_eau_id"], row["pourcentage_tarif"], row["tarifforfaitaire"], annee_tarif
            )
            impute = tarif * nb_t
            if impute <= 0:
                continue
            total += impute
            lignes.append({
                "date": "",
                "reference": "Forfait (estimé)",
                "compte_code": "",
                "compte_nom": "",
                "libelle": row.get("code_point_eau") or "point d'eau forfait",
                "montant_brut": float(tarif),
                "facteur": float(nb_t),
                "montant_impute": float(impute),
                "note": f"tarif trimestriel × {nb_t} trimestre(s)",
            })
    lignes.sort(key=lambda x: x["montant_impute"], reverse=True)
    return total, lignes


def _calc_detail_pour_ouvrage(ctx: ContexteAnalyse, oid, categorie: str, alpha: Decimal):
    """Dispatch commun : lignes élémentaires + total pour un ouvrage et une catégorie
    donnés. Utilisé par construire_detail (1 ouvrage) et construire_detail_commune
    (agrégation sur tous les ouvrages d'une commune)."""
    if categorie in ("salaires_direct", "salaires_hierarchie"):
        variante = "direct" if categorie == "salaires_direct" else "hierarchie"
        return _detail_salaires(ctx, oid, alpha, variante)
    if categorie in ("vehicules_direct", "vehicules_hierarchie"):
        variante = "direct" if categorie == "vehicules_direct" else "hierarchie"
        return _detail_vehicules(ctx, oid, alpha, variante)
    if categorie == "ouvrage_direct":
        return _detail_ouvrage_direct(ctx, oid)
    if categorie == "pieces_planning":
        return _detail_pieces(ctx, oid)
    if categorie == "recette_realisee":
        return _detail_recette_realisee(ctx, oid)
    if categorie == "recette_prevue":
        return _detail_recette_prevue(ctx, oid)
    return D0, []


def construire_detail_commune(
    params: ParamsAnalyse, commune_id: str, categorie: str, reference: date | None = None
) -> dict:
    """Détail d'une catégorie pour une commune : concatène les lignes élémentaires de
    tous ses ouvrages (même méthode que construire_detail, par ouvrage), triées par
    montant imputé décroissant."""
    d1, d2 = resoudre_periode(reference)
    ctx = charger_contexte(d1, d2, params.base_id, params.region_id, params.district_id, params.commune_id)

    ouvrages_commune = [
        oid for oid in ctx.ouvrage_ids if str(ctx.commune_by_ouvrage.get(oid)) == str(commune_id)
    ]
    total = D0
    lignes: list = []
    for oid in ouvrages_commune:
        ouvrage = ctx.ouvrages_by_id.get(oid)
        nom_ouvrage = getattr(ouvrage, "nom_ouvrage", "?")
        t, ls = _calc_detail_pour_ouvrage(ctx, oid, categorie, params.alpha)
        total += t
        for l in ls:
            lignes.append({**l, "libelle": f"[{nom_ouvrage}] {l.get('libelle') or ''}"})
    lignes.sort(key=lambda x: x["montant_impute"], reverse=True)

    if ouvrages_commune:
        commune_nom = ctx.commune_nom_by_id.get(ctx.commune_by_ouvrage.get(ouvrages_commune[0])) or "?"
    else:
        commune_nom = "?"

    periode_fin = ctx.date_fin_recettes if categorie in ("recette_realisee", "recette_prevue") else d2
    return {
        "commune_id": str(commune_id),
        "commune_nom": commune_nom,
        "categorie": categorie,
        "categorie_label": CATEGORIES_DETAIL.get(categorie, categorie),
        "methode": METHODES_DETAIL.get(categorie, ""),
        "periode": {"debut": d1.isoformat(), "fin": periode_fin.isoformat()},
        "alpha": float(params.alpha),
        "total": float(total),
        "nb_lignes": len(lignes),
        "nb_ouvrages": len(ouvrages_commune),
        "lignes": lignes,
    }


def construire_detail(
    params: ParamsAnalyse, ouvrage_id: str, categorie: str, reference: date | None = None
) -> dict:
    d1, d2 = resoudre_periode(reference)
    ctx = charger_contexte(d1, d2, params.base_id, params.region_id, params.district_id, params.commune_id)

    try:
        oid = next(o for o in ctx.ouvrage_ids if str(o) == str(ouvrage_id))
    except StopIteration:
        oid = None

    ouvrage = ctx.ouvrages_by_id.get(oid)
    total, lignes = (D0, []) if oid is None else _calc_detail_pour_ouvrage(ctx, oid, categorie, params.alpha)

    periode_fin = ctx.date_fin_recettes if categorie in ("recette_realisee", "recette_prevue") else d2
    return {
        "ouvrage_id": str(ouvrage_id),
        "ouvrage_nom": getattr(ouvrage, "nom_ouvrage", "?"),
        "categorie": categorie,
        "categorie_label": CATEGORIES_DETAIL.get(categorie, categorie),
        "methode": METHODES_DETAIL.get(categorie, ""),
        "periode": {"debut": d1.isoformat(), "fin": periode_fin.isoformat()},
        "alpha": float(params.alpha),
        "total": float(total),
        "nb_lignes": len(lignes),
        "lignes": lignes,
    }
