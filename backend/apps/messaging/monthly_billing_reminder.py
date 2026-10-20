"""
Selection et regroupement des factures non pointees pour le rappel mensuel
aux responsables d'ouvrage.

Fonctions pures : lecture seule, aucun envoi ni ecriture en base. Reutilisees
par la commande de gestion, la tache Celery et la page de preview admin.
"""
import calendar
from datetime import date

import pytz
from django.db.models import Q
from django.utils import timezone

from apps.billing.models import PaiementForfaitaire, Releve
from apps.employees.models import Employe

TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')

# Les factures anterieures a cette date sont issues d'un ancien systeme
# comptable non fiable/non verifiable et sont exclues du rappel (coherent
# avec le filtre "annee 2025+" deja applique ailleurs dans le projet pour
# les factures impayees, cf. FACTURATION - RAPPEL DES IMPAYES).
DATE_MINIMUM_FACTURES = date(2026, 1, 1)

# Postes dont les titulaires ne doivent jamais recevoir ce rappel, meme s'ils
# sont responsables actifs d'un ouvrage (poste de terrain/execution, pas de
# suivi comptable attendu de leur part).
POSTES_EXCLUS_RAPPEL = ['Superviseur technique', 'Mpikojakoja ifotony']


def date_actuelle_madagascar() -> date:
    """Date du jour en heure de Madagascar (evite date.today() naif)."""
    return timezone.now().astimezone(TZ_MADAGASCAR).date()


def calculer_periode_cible(annee=None, mois=None):
    """
    Determine la periode cible (mois/annee) et sa date de fin.
    Par defaut : le mois qui vient de se terminer (mois precedant la date
    d'execution), coherent avec une execution le 1er du mois suivant.

    Retourne (annee, mois, date_fin_de_periode).
    """
    if annee is None or mois is None:
        aujourd_hui = date_actuelle_madagascar()
        if aujourd_hui.month == 1:
            annee, mois = aujourd_hui.year - 1, 12
        else:
            annee, mois = aujourd_hui.year, aujourd_hui.month - 1

    dernier_jour = calendar.monthrange(annee, mois)[1]  # gere 28/29/30/31
    date_fin = date(annee, mois, dernier_jour)
    return annee, mois, date_fin


def releves_non_pointes(date_fin_periode: date):
    """Releve non pointes (numeroDiameX vide) avec datereleve entre
    DATE_MINIMUM_FACTURES et la fin de periode, rattaches a un point d'eau
    et un ouvrage identifiables.

    Exclut les factures a montant nul/absent (rien a pointer) et les
    releves dont la remarque signale un point d'eau coupe (meme pattern que
    la page Recoupement : icontains insensible a la casse)."""
    return (
        Releve.objects
        .filter(datereleve__gte=DATE_MINIMUM_FACTURES, datereleve__lte=date_fin_periode)
        .filter(Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact=''))
        .filter(point_eau__isnull=False, point_eau__ouvrage__isnull=False)
        .filter(montant__isnull=False)
        .exclude(montant=0)
        .exclude(remarque__icontains='coupé')
        .select_related('point_eau', 'point_eau__ouvrage')
    )


def paiements_forfaitaires_non_pointes(date_fin_periode: date):
    """PaiementForfaitaire non pointes (numeroDiameX OU baseDiameX vide)
    avec date_facture entre DATE_MINIMUM_FACTURES et la fin de periode,
    rattaches a un ouvrage identifiable.

    Exclut les factures a montant nul/absent (rien a pointer)."""
    return (
        PaiementForfaitaire.objects
        .filter(date_facture__gte=DATE_MINIMUM_FACTURES, date_facture__lte=date_fin_periode)
        .filter(
            Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
            | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
        )
        .filter(point_eau__ouvrage__isnull=False)
        .filter(montant__isnull=False)
        .exclude(montant=0)
        .select_related('point_eau', 'point_eau__ouvrage')
    )


def compter_factures_sans_responsable(date_fin_periode: date) -> int:
    """Compte les factures non pointees (hors exclusions montant nul / point
    d'eau coupe) dont le point d'eau ou l'ouvrage est absent, donc
    impossible a rattacher a un responsable via EmployeOuvrages."""
    releves_orphelins = (
        Releve.objects
        .filter(datereleve__gte=DATE_MINIMUM_FACTURES, datereleve__lte=date_fin_periode)
        .filter(Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact=''))
        .filter(Q(point_eau__isnull=True) | Q(point_eau__ouvrage__isnull=True))
        .filter(montant__isnull=False)
        .exclude(montant=0)
        .exclude(remarque__icontains='coupé')
        .count()
    )
    forfaitaires_orphelins = (
        PaiementForfaitaire.objects
        .filter(date_facture__gte=DATE_MINIMUM_FACTURES, date_facture__lte=date_fin_periode)
        .filter(
            Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
            | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
        )
        .filter(point_eau__ouvrage__isnull=True)
        .filter(montant__isnull=False)
        .exclude(montant=0)
        .count()
    )
    return releves_orphelins + forfaitaires_orphelins


def responsables_actifs_pour_ouvrage(ouvrage_id, date_reference: date):
    """
    Retourne les Employe responsables actifs (recevoir_alertes=True) d'un
    ouvrage a une date de reference donnee.

    Reimplementation explicite (pas d'utilisation de la property est_actif
    d'EmployeOuvrages) car cette derniere utilise date.today() naif et ne
    verifie pas date_debut.

    Exclut les employes debauches (date_debauchage renseignee, meme pattern
    que _filter_active_employes_queryset dans apps.employees.views) et les
    titulaires des postes de terrain listes dans POSTES_EXCLUS_RAPPEL.
    """
    return Employe.objects.filter(
        ouvrages_responsable__ouvrage_id=ouvrage_id,
        ouvrages_responsable__recevoir_alertes=True,
        ouvrages_responsable__date_debut__lte=date_reference,
        date_debauchage__isnull=True,
    ).filter(
        Q(ouvrages_responsable__date_fin__isnull=True)
        | Q(ouvrages_responsable__date_fin__gte=date_reference)
    ).exclude(
        poste__nom_poste__in=POSTES_EXCLUS_RAPPEL
    ).distinct()


def superieurs_hierarchiques(employe, date_reference: date):
    """
    Retourne la liste des superieurs hierarchiques actifs de employe a une
    date de reference donnee, du plus direct (N+1) au plus haut (sommet de
    la chaine trouvee).

    Reimplementation explicite (pas d'utilisation de la property
    Employe.ascendants) car cette derniere s'appuie sur
    Employe.superieur_hierarchique qui utilise timezone.now().date() au lieu
    d'une date de reference injectable — incoherent avec le reste de ce
    module qui raisonne toujours sur date_fin_periode.

    Protection anti-boucle : une chaine mal saisie (A supervise B supervise
    A) ne provoque jamais de boucle infinie.

    Un superieur debauche (date_debauchage renseignee) ou occupant un poste
    de POSTES_EXCLUS_RAPPEL est saute (jamais notifie) mais n'interrompt pas
    la remontee vers les niveaux suivants.
    """
    from apps.employees.models import HierarchieEmploye

    superieurs = []
    visites = {employe.id}
    courant = employe

    while True:
        relation = HierarchieEmploye.objects.filter(
            employe=courant, date_debut__lte=date_reference,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=date_reference)
        ).select_related('superieur', 'superieur__poste').first()

        if relation is None or relation.superieur_id in visites:
            break

        superieur = relation.superieur
        visites.add(superieur.id)

        est_exclu = (
            superieur.date_debauchage is not None
            or (superieur.poste and superieur.poste.nom_poste in POSTES_EXCLUS_RAPPEL)
        )
        if not est_exclu:
            superieurs.append(superieur)

        courant = superieur

    return superieurs


def construire_regroupement_hierarchique(regroupement: dict, date_reference: date) -> dict:
    """
    A partir du regroupement employe -> ouvrages (construire_regroupement),
    construit une vue complementaire superieur -> subordonnes concernes,
    pour notifier pour information les responsables hierarchiques.

    Structure retournee :
    {
        superieur_id: {
            'employe': Employe (le superieur),
            'subordonnes': {
                employe_id: entree_du_regroupement (meme structure que
                    regroupement[employe_id] : {'employe', 'ouvrages': {...}}),
                ...
            },
        },
        ...
    }

    Un meme superieur peut apparaitre pour plusieurs subordonnes distincts
    (agrege dans 'subordonnes'), et un meme employe peut remonter vers
    plusieurs niveaux de superieurs (chacun recoit sa propre entree).
    """
    regroupement_hierarchique = {}

    for employe_id, entree in regroupement.items():
        employe = entree['employe']
        for superieur in superieurs_hierarchiques(employe, date_reference):
            entree_superieur = regroupement_hierarchique.setdefault(superieur.id, {
                'employe': superieur,
                'subordonnes': {},
            })
            entree_superieur['subordonnes'][employe_id] = entree

    return regroupement_hierarchique


def _ajouter_ligne(regroupement, employe, ouvrage, point_eau, ligne):
    entree_employe = regroupement.setdefault(employe.id, {
        'employe': employe,
        'ouvrages': {},
    })
    entree_ouvrage = entree_employe['ouvrages'].setdefault(ouvrage.id, {
        'ouvrage': ouvrage,
        'points_eau': {},
    })
    entree_point_eau = entree_ouvrage['points_eau'].setdefault(point_eau.id, {
        'point_eau': point_eau,
        'lignes': [],
    })
    entree_point_eau['lignes'].append(ligne)


def construire_regroupement(annee: int, mois: int) -> dict:
    """
    Construit le regroupement complet : employe responsable -> ouvrage ->
    point d'eau -> lignes de factures non pointees (Releve et
    PaiementForfaitaire melanges).

    Un meme point d'eau peut recevoir des lignes des deux types. Un meme
    ouvrage peut avoir plusieurs responsables actifs simultanement (chacun
    recoit sa propre entree dans le regroupement).
    """
    _, _, date_fin_periode = calculer_periode_cible(annee, mois)
    date_reference = date_fin_periode

    regroupement = {}
    responsables_par_ouvrage = {}

    def _responsables_pour(ouvrage_id):
        if ouvrage_id not in responsables_par_ouvrage:
            responsables_par_ouvrage[ouvrage_id] = list(
                responsables_actifs_pour_ouvrage(ouvrage_id, date_reference)
            )
        return responsables_par_ouvrage[ouvrage_id]

    for releve in releves_non_pointes(date_fin_periode):
        point_eau = releve.point_eau
        ouvrage = point_eau.ouvrage
        ligne = {
            'type': 'releve',
            'objet': releve,
            'date': releve.datereleve,
            'montant': releve.montant,
        }
        for employe in _responsables_pour(ouvrage.id):
            _ajouter_ligne(regroupement, employe, ouvrage, point_eau, ligne)

    for paiement in paiements_forfaitaires_non_pointes(date_fin_periode):
        point_eau = paiement.point_eau
        ouvrage = point_eau.ouvrage
        ligne = {
            'type': 'forfaitaire',
            'objet': paiement,
            'date': paiement.date_facture,
            'montant': paiement.montant,
        }
        for employe in _responsables_pour(ouvrage.id):
            _ajouter_ligne(regroupement, employe, ouvrage, point_eau, ligne)

    return regroupement
