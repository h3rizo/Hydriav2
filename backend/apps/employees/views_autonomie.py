"""
Vues et API pour le module de grille salariale par stade d'autonomie.

Toutes les vues sont reservees aux postes RH/Direction (has_admin_access).
Les endpoints JSON retournent un 403 JSON explicite (plus adapte a une API
qu'HttpResponseForbidden en HTML, utilise par le decorateur @admin_required
classique pour la page HTML principale).
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .decorators import admin_required
from .models import ConfigSalaire, Employe, GrilleSalaire, Poste, Salaire
from .models_autonomie import (
    GrilleAutonomie,
    HistoriqueStadeAutonomie,
    IndicateurPrime,
    MajorationTerritoriale,
    PalierPrime,
    RegleDePrime,
    ResultatIndicateur,
    SimulationRemuneration,
    StadeAutonomie,
)
from .permissions import has_admin_access
from .services_controles_coherence import calculer_alertes_coherence
from .services_primes import calculer_toutes_primes_employe
from .views_grilles_salariales import _get_request_organisation, _parse_date


# ============================================================
# Utilitaires (reponse JSON 403, parsing, scoping)
# ============================================================

def _require_admin_json(request):
    """Retourne une JsonResponse 403 si l'utilisateur n'a pas les droits admin, sinon None."""
    if not has_admin_access(request.user):
        return JsonResponse({
            'success': False,
            'error': "Acces refuse. Cette fonctionnalite est reservee aux postes d'administration.",
        }, status=403)
    return None


def _parse_decimal(value, allow_none=True):
    if value in (None, ''):
        if allow_none:
            return None
        raise ValidationError("Cette valeur numerique est obligatoire.")
    try:
        return Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"Valeur numerique invalide: {value}")


def _parse_bool(value, defaut=False):
    if value in (None, ''):
        return defaut
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'on', 'oui', 'yes')


def _pivot_stade_ordre(request):
    """Ordre du stade pivot (declenche_anciennete) le plus bas dans le scope, ou None."""
    pivot = _scoped_stades(request).filter(declenche_anciennete=True).order_by('ordre').first()
    return pivot.ordre if pivot else None


def _assurer_pivot_unique(stade):
    """Un seul stade pivot par organisation : decoche les autres si celui-ci est coche."""
    if not stade.declenche_anciennete:
        return
    StadeAutonomie.objects.filter(
        organisation_id=stade.organisation_id,
        declenche_anciennete=True,
    ).exclude(pk=stade.pk).update(declenche_anciennete=False)


def _apply_anciennete_payload(grille, data):
    """Applique les champs d'anciennete presents dans le payload sur une grille."""
    if 'anciennete_activee' in data:
        grille.anciennete_activee = _parse_bool(data.get('anciennete_activee'))
    if 'anciennete_taux_annuel_pct' in data:
        grille.anciennete_taux_annuel_pct = _parse_decimal(data.get('anciennete_taux_annuel_pct'))
    if 'anciennete_mode_capitalisation' in data and data.get('anciennete_mode_capitalisation'):
        grille.anciennete_mode_capitalisation = data['anciennete_mode_capitalisation']
    if 'anciennete_seuil_annees' in data:
        grille.anciennete_seuil_annees = _parse_decimal(data.get('anciennete_seuil_annees')) or Decimal('0')
    if 'anciennete_plafond_annees' in data:
        grille.anciennete_plafond_annees = _parse_decimal(data.get('anciennete_plafond_annees'))
    if 'anciennete_plafond_majoration_pct' in data:
        grille.anciennete_plafond_majoration_pct = _parse_decimal(data.get('anciennete_plafond_majoration_pct'))


def _scoped_stades(request):
    queryset = StadeAutonomie.objects.select_related('organisation').all()
    if getattr(request.user, 'is_superuser', False):
        return queryset
    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(models.Q(organisation=organisation) | models.Q(organisation__isnull=True))


def _scoped_grilles_autonomie(request):
    queryset = GrilleAutonomie.objects.select_related('poste__organisation', 'stade', 'organisation').all()
    if getattr(request.user, 'is_superuser', False):
        return queryset
    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(
        models.Q(organisation=organisation) |
        models.Q(organisation__isnull=True, poste__organisation=organisation)
    )


def _scoped_regles_primes(request):
    queryset = RegleDePrime.objects.select_related('poste__organisation', 'stade', 'organisation').all()
    if getattr(request.user, 'is_superuser', False):
        return queryset
    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(
        models.Q(organisation=organisation) |
        models.Q(organisation__isnull=True, poste__organisation=organisation)
    )


def _scoped_majorations(request):
    queryset = MajorationTerritoriale.objects.select_related('district', 'base', 'compte', 'organisation').all()
    if getattr(request.user, 'is_superuser', False):
        return queryset
    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(models.Q(organisation=organisation) | models.Q(organisation__isnull=True))


def _scoped_bases_majorations(request):
    from apps.organization.models import Base as BaseModel

    queryset = BaseModel.objects.select_related('organisation').all()
    if getattr(request.user, 'is_superuser', False):
        return queryset
    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(organisation=organisation)


def _scoped_postes_autonomie(request):
    from .views_grilles_salariales import _scoped_postes
    return _scoped_postes(request).filter(mode_reference_salariale='autonomie')


def _scoped_employes_simulateur(request):
    queryset = Employe.objects.select_related(
        'poste', 'base', 'base__organisation', 'stade_autonomie_actuel',
    )
    if getattr(request.user, 'is_superuser', False):
        return queryset
    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(base__organisation=organisation)


def _dernier_salaire_net_par_employe(employe_ids):
    """
    Retourne {employe_id: (salaire_net_paye: Decimal, date_paiement: date)} pour le
    dernier bulletin paye de chaque employe (le plus recent, sur n'importe quel contrat).
    """
    if not employe_ids:
        return {}
    salaires_qs = (
        Salaire.objects.filter(grille_salaire__contrat__employe_id__in=employe_ids)
        .select_related('grille_salaire__contrat')
        .order_by('grille_salaire__contrat__employe_id', '-date_paiement')
        .distinct('grille_salaire__contrat__employe_id')
    )
    resultat = {}
    for salaire in salaires_qs:
        employe_id = salaire.grille_salaire.contrat.employe_id
        resultat[employe_id] = (salaire.salaire_net_paye, salaire.date_paiement)
    return resultat


def _positionner_employes_par_stade(request):
    """
    Pour chaque employe actif (avec poste renseigne), determine le stade dont le
    salaire net fixe (grille appliquee) est le plus proche de son dernier salaire
    net reellement paye. Ceci est une estimation indicative: le stade "officiel"
    reste celui valide par evaluation (employe.stade_autonomie_actuel).

    Retourne {(poste_id, stade_id): [ {employe...}, ... ]}
    """
    employes_qs = _scoped_employes_simulateur(request).filter(
        salarie=True, poste__isnull=False,
    ).filter(
        models.Q(date_debauchage__isnull=True) | models.Q(date_debauchage__gte=date.today())
    ).select_related('poste', 'stade_autonomie_actuel').prefetch_related(
        'historique_stades_autonomie__stade'
    )

    config = ConfigSalaire.get_config()
    pivot_stade = _scoped_stades(request).filter(declenche_anciennete=True).order_by('ordre').first()
    pivot_ordre = pivot_stade.ordre if pivot_stade else None

    employes = list(employes_qs)
    employe_ids = [e.id for e in employes]
    salaire_by_employe = _dernier_salaire_net_par_employe(employe_ids)

    poste_ids = {e.poste_id for e in employes if e.poste_id}
    # Grille de reference par (poste, stade): idealement 'appliquee', sinon la
    # meilleure candidate disponible (validee > soumise > brouillon), la plus
    # recente en cas d'egalite. Les grilles 'rejetee' sont exclues.
    priorite_statut = {'appliquee': 0, 'validee': 1, 'soumise': 2, 'brouillon': 3}
    grilles = (
        _scoped_grilles_autonomie(request)
        .filter(poste_id__in=poste_ids)
        .exclude(statut='rejetee')
        .select_related('stade')
    )
    meilleure_grille_par_cle = {}
    for grille in grilles:
        cle = (grille.poste_id, grille.stade_id)
        actuelle = meilleure_grille_par_cle.get(cle)
        if actuelle is None:
            meilleure_grille_par_cle[cle] = grille
            continue
        rang_nouvelle = priorite_statut.get(grille.statut, 9)
        rang_actuelle = priorite_statut.get(actuelle.statut, 9)
        if rang_nouvelle < rang_actuelle or (
            rang_nouvelle == rang_actuelle
            and grille.date_debut_validite > actuelle.date_debut_validite
        ):
            meilleure_grille_par_cle[cle] = grille

    grilles_par_poste = {}
    for (poste_id, _stade_id), grille in meilleure_grille_par_cle.items():
        grilles_par_poste.setdefault(poste_id, []).append(grille)

    resultat = {}
    for employe in employes:
        salaire_info = salaire_by_employe.get(employe.id)
        if salaire_info is None or not employe.poste_id:
            continue
        salaire_net, date_paiement = salaire_info
        candidats = grilles_par_poste.get(employe.poste_id) or []
        if not candidats:
            continue

        salaire_net_float = float(salaire_net or 0)
        meilleure_grille = min(
            candidats,
            key=lambda g: abs(float(g.salaire_net_fixe) - salaire_net_float),
        )
        ecart = salaire_net_float - float(meilleure_grille.salaire_net_fixe)

        # Anciennete "au sommet de grille" : date du 1er acces a un stade >= pivot.
        date_debut_anciennete = None
        anciennete_annees = 0.0
        net_avec_anciennete = None
        if pivot_ordre is not None:
            entrees = sorted(
                (h for h in employe.historique_stades_autonomie.all()
                 if h.stade and h.stade.ordre >= pivot_ordre),
                key=lambda h: h.date_effet,
            )
            if entrees:
                date_debut_anciennete = entrees[0].date_effet
                jours = (date.today() - date_debut_anciennete).days
                if jours > 0:
                    anciennete_annees = round(jours / 365.25, 2)
                if meilleure_grille.anciennete_activee and meilleure_grille.stade and meilleure_grille.stade.ordre >= pivot_ordre:
                    net_avec_anciennete = float(
                        meilleure_grille.net_effectif(Decimal(str(anciennete_annees)), config)
                    )

        cle = (str(employe.poste_id), str(meilleure_grille.stade_id))
        resultat.setdefault(cle, []).append({
            'date_debut_anciennete': date_debut_anciennete.isoformat() if date_debut_anciennete else None,
            'anciennete_autonomie_annees': anciennete_annees,
            'net_avec_anciennete': net_avec_anciennete,
            'employe_id': str(employe.id),
            'surnom': (employe.surnom or '').strip(),
            'nom_affichage': employe.nom_affichage,
            'poste_id': str(employe.poste_id),
            'poste_nom': employe.poste.nom_poste,
            'stade_declare_id': str(employe.stade_autonomie_actuel_id) if employe.stade_autonomie_actuel_id else None,
            'stade_declare_nom': employe.stade_autonomie_actuel.nom_stade if employe.stade_autonomie_actuel_id else None,
            'stade_estime_id': str(meilleure_grille.stade_id),
            'stade_estime_nom': meilleure_grille.stade.nom_stade,
            'salaire_net_reel': salaire_net_float,
            'date_paiement': date_paiement.isoformat() if date_paiement else None,
            'salaire_grille_reference': float(meilleure_grille.salaire_net_fixe),
            'grille_reference_statut': meilleure_grille.statut,
            'ecart_ariary': ecart,
            'ecart_pct': (ecart / float(meilleure_grille.salaire_net_fixe) * 100) if meilleure_grille.salaire_net_fixe else None,
            'coherent': (
                employe.stade_autonomie_actuel_id is not None
                and str(employe.stade_autonomie_actuel_id) == str(meilleure_grille.stade_id)
            ),
        })

    return resultat


# ============================================================
# Serialisation
# ============================================================

def _serialize_stade(stade):
    return {
        'id': str(stade.id),
        'organisation_id': str(stade.organisation_id) if stade.organisation_id else None,
        'nom_stade': stade.nom_stade,
        'ordre': stade.ordre,
        'description': stade.description or '',
        'couleur_hex': stade.couleur_hex or '',
        'declenche_anciennete': stade.declenche_anciennete,
    }


def _serialize_grille_autonomie(grille):
    return {
        'id': str(grille.id),
        'poste_id': str(grille.poste_id),
        'poste_nom': grille.poste.nom_poste if grille.poste_id else None,
        'poste_categorie_professionnelle': grille.poste.get_categorie_professionnelle_display() if grille.poste_id and grille.poste.categorie_professionnelle else None,
        'poste_competences_attributions': grille.poste.competences_attributions if grille.poste_id else None,
        'poste_type': grille.poste.type_poste if grille.poste_id else None,
        'poste_niveau': grille.poste.niveau_poste if grille.poste_id else None,
        'stade_id': str(grille.stade_id),
        'stade_nom': grille.stade.nom_stade if grille.stade_id else None,
        'stade_ordre': grille.stade.ordre if grille.stade_id else None,
        'salaire_net_fixe': float(grille.salaire_net_fixe),
        'prime_cible': float(grille.prime_cible),
        'prime_maximale': float(grille.prime_maximale),
        'remuneration_cible': float(grille.remuneration_cible),
        'remuneration_maximale': float(grille.remuneration_maximale),
        'statut': grille.statut,
        'statut_display': grille.get_statut_display(),
        'date_debut_validite': grille.date_debut_validite.isoformat() if grille.date_debut_validite else None,
        'date_fin_validite': grille.date_fin_validite.isoformat() if grille.date_fin_validite else None,
        'version_precedente_id': str(grille.version_precedente_id) if grille.version_precedente_id else None,
        'stade_declenche_anciennete': grille.stade.declenche_anciennete if grille.stade_id else False,
        'anciennete_activee': grille.anciennete_activee,
        'anciennete_taux_annuel_pct': float(grille.anciennete_taux_annuel_pct) if grille.anciennete_taux_annuel_pct is not None else None,
        'anciennete_mode_capitalisation': grille.anciennete_mode_capitalisation,
        'anciennete_seuil_annees': float(grille.anciennete_seuil_annees) if grille.anciennete_seuil_annees is not None else 0,
        'anciennete_plafond_annees': float(grille.anciennete_plafond_annees) if grille.anciennete_plafond_annees is not None else None,
        'anciennete_plafond_majoration_pct': float(grille.anciennete_plafond_majoration_pct) if grille.anciennete_plafond_majoration_pct is not None else None,
    }


def _serialize_palier(palier):
    return {
        'id': str(palier.id),
        'taux_realisation_min': float(palier.taux_realisation_min),
        'taux_realisation_max': float(palier.taux_realisation_max) if palier.taux_realisation_max is not None else None,
        'taux_prime': float(palier.taux_prime),
    }


def _serialize_indicateur(indicateur):
    return {
        'id': str(indicateur.id),
        'nom_indicateur': indicateur.nom_indicateur,
        'unite': indicateur.unite or '',
        'ponderation': float(indicateur.ponderation),
        'objectif': float(indicateur.objectif),
        'seuil_minimum': float(indicateur.seuil_minimum) if indicateur.seuil_minimum is not None else None,
        'ordre': indicateur.ordre,
        'paliers': [_serialize_palier(p) for p in indicateur.paliers.all().order_by('taux_realisation_min')],
    }


def _serialize_regle_prime(regle):
    return {
        'id': str(regle.id),
        'poste_id': str(regle.poste_id),
        'poste_nom': regle.poste.nom_poste if regle.poste_id else None,
        'stade_id': str(regle.stade_id) if regle.stade_id else None,
        'stade_nom': regle.stade.nom_stade if regle.stade_id else None,
        'nom_regle': regle.nom_regle,
        'type_calcul': regle.type_calcul,
        'type_calcul_display': regle.get_type_calcul_display(),
        'montant_fixe': float(regle.montant_fixe) if regle.montant_fixe is not None else None,
        'pourcentage_salaire': float(regle.pourcentage_salaire) if regle.pourcentage_salaire is not None else None,
        'periodicite': regle.periodicite,
        'periodicite_display': regle.get_periodicite_display(),
        'plafond': float(regle.plafond) if regle.plafond is not None else None,
        'actif': regle.actif,
        'statut': regle.statut,
        'statut_display': regle.get_statut_display(),
        'date_debut_validite': regle.date_debut_validite.isoformat() if regle.date_debut_validite else None,
        'date_fin_validite': regle.date_fin_validite.isoformat() if regle.date_fin_validite else None,
        'indicateurs': [_serialize_indicateur(i) for i in regle.indicateurs.all().order_by('ordre')],
    }


def _serialize_majoration(majoration):
    return {
        'id': str(majoration.id),
        'nom': majoration.nom,
        'district_id': str(majoration.district_id) if majoration.district_id else None,
        'district_nom': majoration.district.nom_district if majoration.district_id else None,
        'base_id': str(majoration.base_id) if majoration.base_id else None,
        'base_nom': majoration.base.nom_base if majoration.base_id else None,
        'type_montant': majoration.type_montant,
        'montant_fixe': float(majoration.montant_fixe) if majoration.montant_fixe is not None else None,
        'pourcentage_salaire': float(majoration.pourcentage_salaire) if majoration.pourcentage_salaire is not None else None,
        'compte_id': str(majoration.compte_id) if majoration.compte_id else None,
        'actif': majoration.actif,
        'date_debut_validite': majoration.date_debut_validite.isoformat() if majoration.date_debut_validite else None,
        'date_fin_validite': majoration.date_fin_validite.isoformat() if majoration.date_fin_validite else None,
    }


# ============================================================
# Page principale
# ============================================================

@login_required
@admin_required
def grilles_autonomie_home(request):
    """Page principale du module grille par autonomie (tableau + graphique + regles + majorations + simulateur)."""
    organisation = _get_request_organisation(request)
    postes_data = [
        {
            'id': str(p.id),
            'nom_poste': p.nom_poste,
            'mode_reference_salariale': p.mode_reference_salariale,
            'type_poste': p.type_poste,
            'niveau_poste': p.niveau_poste,
        }
        for p in _scoped_postes_autonomie(request).order_by('ordre_affichage', 'nom_poste')
    ]
    stades_data = [_serialize_stade(s) for s in _scoped_stades(request)]
    employes_qs = _scoped_employes_simulateur(request).filter(
        salarie=True,
    ).filter(
        models.Q(date_debauchage__isnull=True) | models.Q(date_debauchage__gte=date.today())
    ).order_by('surnom', 'nom', 'prenom')
    employes_data = [
        {
            'id': str(employe.id),
            'surnom': (employe.surnom or '').strip(),
            'nom_affichage': employe.nom_affichage,
            'nom_complet': employe.nom_complet,
            'poste_nom': employe.poste.nom_poste if employe.poste_id else '',
            'base_nom': employe.base.nom_base if employe.base_id else '',
            'organisation_nom': (
                employe.base.organisation.nom_organisation
                if employe.base_id and employe.base.organisation_id else ''
            ),
            'stade_nom': (
                employe.stade_autonomie_actuel.nom_stade
                if employe.stade_autonomie_actuel_id else ''
            ),
        }
        for employe in employes_qs
    ]
    bases_data = [
        {
            'id': str(base.id),
            'nom': base.nom_base,
            'organisation_nom': base.organisation.nom_organisation,
        }
        for base in _scoped_bases_majorations(request).order_by(
            'organisation__nom_organisation', 'nom_base'
        )
    ]
    from apps.geography.models import District
    districts_data = [
        {
            'id': str(district.id),
            'nom': district.nom_district,
            'region_nom': district.region.nom_region,
        }
        for district in District.objects.select_related('region').order_by(
            'region__nom_region', 'nom_district'
        )
    ]

    config = ConfigSalaire.get_config()
    anciennete_config = {
        'taux_defaut_pct': float(config.taux_anciennete_autonomie_defaut_pct)
        if config.taux_anciennete_autonomie_defaut_pct is not None else None,
        'plafond_annees_defaut': float(config.plafond_anciennete_autonomie_annees)
        if config.plafond_anciennete_autonomie_annees is not None else None,
        'pivot_stade_ordre': _pivot_stade_ordre(request),
    }

    context = {
        'postes_data': postes_data,
        'stades_data': stades_data,
        'employes_data': employes_data,
        'bases_data': bases_data,
        'districts_data': districts_data,
        'anciennete_config': anciennete_config,
        'can_manage': getattr(request.user, 'is_superuser', False) or organisation is not None,
    }
    return render(request, 'employees/grilles_autonomie.html', context)


# ============================================================
# CRUD Stades d'autonomie
# ============================================================

@login_required
def api_stades_list(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    stades = _scoped_stades(request)
    return JsonResponse({'success': True, 'stades': [_serialize_stade(s) for s in stades]})


@login_required
def api_stades_create(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        organisation = _get_request_organisation(request)
        stade = StadeAutonomie(
            organisation=organisation,
            nom_stade=data.get('nom_stade', '').strip(),
            ordre=int(data.get('ordre', 0)),
            description=data.get('description', ''),
            couleur_hex=data.get('couleur_hex', ''),
            declenche_anciennete=_parse_bool(data.get('declenche_anciennete')),
        )
        stade.full_clean()
        stade.save()
        _assurer_pivot_unique(stade)
        return JsonResponse({'success': True, 'stade': _serialize_stade(stade)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_stades_update(request, stade_id):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    stade = get_object_or_404(_scoped_stades(request), id=stade_id)
    try:
        data = json.loads(request.body)
        if 'nom_stade' in data:
            stade.nom_stade = data['nom_stade'].strip()
        if 'ordre' in data:
            stade.ordre = int(data['ordre'])
        if 'description' in data:
            stade.description = data['description']
        if 'couleur_hex' in data:
            stade.couleur_hex = data['couleur_hex']
        if 'declenche_anciennete' in data:
            stade.declenche_anciennete = _parse_bool(data['declenche_anciennete'])
        stade.full_clean()
        stade.save()
        _assurer_pivot_unique(stade)
        return JsonResponse({'success': True, 'stade': _serialize_stade(stade)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_stades_delete(request, stade_id):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    stade = get_object_or_404(_scoped_stades(request), id=stade_id)
    if GrilleAutonomie.objects.filter(stade=stade, statut='appliquee').exists():
        return JsonResponse({
            'success': False,
            'error': "Ce stade est reference par une grille appliquee et ne peut pas etre supprime.",
        }, status=400)
    stade.delete()
    return JsonResponse({'success': True})


@login_required
def api_stades_reorder(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        ordres = data.get('ordres', [])  # [{'id': ..., 'ordre': ...}, ...]
        stades_qs = _scoped_stades(request)
        with transaction.atomic():
            for item in ordres:
                stade = stades_qs.filter(id=item['id']).first()
                if stade:
                    stade.ordre = int(item['ordre'])
                    stade.save(update_fields=['ordre'])
        return JsonResponse({'success': True})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ============================================================
# CRUD Grille autonomie
# ============================================================

@login_required
def api_grilles_autonomie_list(request):
    denied = _require_admin_json(request)
    if denied:
        return denied

    queryset = _scoped_grilles_autonomie(request)
    poste_id = request.GET.get('poste_id')
    stade_id = request.GET.get('stade_id')
    statut = request.GET.get('statut')
    type_poste = request.GET.get('type_poste')
    niveau_poste = request.GET.get('niveau_poste')
    if poste_id:
        queryset = queryset.filter(poste_id=poste_id)
    if stade_id:
        queryset = queryset.filter(stade_id=stade_id)
    if statut:
        queryset = queryset.filter(statut=statut)
    if type_poste:
        queryset = queryset.filter(poste__type_poste=type_poste)
    if niveau_poste:
        queryset = queryset.filter(poste__niveau_poste=niveau_poste)

    grilles = queryset.order_by('poste__ordre_affichage', 'poste__nom_poste', 'stade__ordre')
    return JsonResponse({
        'success': True,
        'grilles': [_serialize_grille_autonomie(g) for g in grilles],
        'pivot_stade_ordre': _pivot_stade_ordre(request),
    })


@login_required
def api_grilles_autonomie_create(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        organisation = _get_request_organisation(request)
        poste = get_object_or_404(_scoped_postes_autonomie(request), id=data['poste_id'])
        stade = get_object_or_404(_scoped_stades(request), id=data['stade_id'])

        employe = getattr(request.user, 'employe', None)

        grille = GrilleAutonomie(
            poste=poste,
            stade=stade,
            organisation=organisation,
            salaire_net_fixe=_parse_decimal(data.get('salaire_net_fixe'), allow_none=False),
            prime_cible=_parse_decimal(data.get('prime_cible')) or Decimal('0'),
            prime_maximale=_parse_decimal(data.get('prime_maximale')) or Decimal('0'),
            date_debut_validite=_parse_date(data.get('date_debut_validite')) or date.today(),
            date_fin_validite=_parse_date(data.get('date_fin_validite')),
            statut='brouillon',
            createur=employe,
        )
        _apply_anciennete_payload(grille, data)
        grille.full_clean()
        grille.save()
        return JsonResponse({'success': True, 'grille': _serialize_grille_autonomie(grille)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except KeyError as exc:
        return JsonResponse({'success': False, 'error': f'Champ obligatoire manquant: {exc}'}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_grilles_autonomie_update(request, grille_id):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    grille = get_object_or_404(_scoped_grilles_autonomie(request), id=grille_id)
    if grille.statut == 'appliquee':
        return JsonResponse({
            'success': False,
            'error': "Cette grille est appliquee. Creez une nouvelle version pour la modifier.",
        }, status=400)

    try:
        data = json.loads(request.body)
        if 'salaire_net_fixe' in data:
            grille.salaire_net_fixe = _parse_decimal(data['salaire_net_fixe'], allow_none=False)
        if 'prime_cible' in data:
            grille.prime_cible = _parse_decimal(data['prime_cible']) or Decimal('0')
        if 'prime_maximale' in data:
            grille.prime_maximale = _parse_decimal(data['prime_maximale']) or Decimal('0')
        if 'date_debut_validite' in data:
            grille.date_debut_validite = _parse_date(data['date_debut_validite']) or grille.date_debut_validite
        if 'date_fin_validite' in data:
            grille.date_fin_validite = _parse_date(data['date_fin_validite'])
        _apply_anciennete_payload(grille, data)
        grille.full_clean()
        grille.save()
        return JsonResponse({'success': True, 'grille': _serialize_grille_autonomie(grille)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_grilles_autonomie_delete(request, grille_id):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    grille = get_object_or_404(_scoped_grilles_autonomie(request), id=grille_id)
    if grille.statut != 'brouillon':
        return JsonResponse({'success': False, 'error': 'Seules les grilles en brouillon peuvent etre supprimees.'}, status=400)
    grille.delete()
    return JsonResponse({'success': True})


def _workflow_action(request, grille_id, action):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    grille = get_object_or_404(_scoped_grilles_autonomie(request), id=grille_id)
    employe = getattr(request.user, 'employe', None)

    try:
        data = json.loads(request.body) if request.body else {}
        commentaire = data.get('commentaire', '')

        if action == 'soumettre':
            grille.soumettre()
        elif action == 'valider':
            grille.valider(employe, commentaire)
        elif action == 'rejeter':
            grille.rejeter(employe, commentaire)
        elif action == 'appliquer':
            date_application = _parse_date(data.get('date_application'))
            grille.appliquer(date_application)

        return JsonResponse({'success': True, 'grille': _serialize_grille_autonomie(grille)})
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_grilles_autonomie_soumettre(request, grille_id):
    return _workflow_action(request, grille_id, 'soumettre')


@login_required
def api_grilles_autonomie_valider(request, grille_id):
    return _workflow_action(request, grille_id, 'valider')


@login_required
def api_grilles_autonomie_rejeter(request, grille_id):
    return _workflow_action(request, grille_id, 'rejeter')


@login_required
def api_grilles_autonomie_appliquer(request, grille_id):
    return _workflow_action(request, grille_id, 'appliquer')


@login_required
def api_grilles_autonomie_soumettre_lot(request):
    """Soumet en lot tous les brouillons d'une session d'edition (ex: apres edition graphique)."""
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        grille_ids = data.get('grille_ids', [])
        queryset = _scoped_grilles_autonomie(request).filter(id__in=grille_ids, statut='brouillon')

        soumises = []
        erreurs = []
        with transaction.atomic():
            for grille in queryset:
                try:
                    grille.soumettre()
                    soumises.append(str(grille.id))
                except Exception as exc:
                    erreurs.append({'grille_id': str(grille.id), 'error': str(exc)})

        return JsonResponse({'success': True, 'soumises': soumises, 'erreurs': erreurs})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ============================================================
# Donnees du graphique
# ============================================================

@login_required
def api_graphique_donnees(request):
    denied = _require_admin_json(request)
    if denied:
        return denied

    postes_qs = _scoped_postes_autonomie(request)
    poste_id = request.GET.get('poste_id')
    type_poste = request.GET.get('type_poste')
    niveau_poste = request.GET.get('niveau_poste')
    if poste_id:
        postes_qs = postes_qs.filter(id=poste_id)
    if type_poste:
        postes_qs = postes_qs.filter(type_poste=type_poste)
    if niveau_poste:
        postes_qs = postes_qs.filter(niveau_poste=niveau_poste)

    stades = list(_scoped_stades(request).order_by('ordre'))
    inclure_employes = request.GET.get('avec_employes') == '1'
    employes_par_cle = _positionner_employes_par_stade(request) if inclure_employes else {}
    resultat = []

    config = ConfigSalaire.get_config()
    pivot_ordre = _pivot_stade_ordre(request)
    try:
        anciennete_projection = Decimal(str(request.GET.get('anciennete_projection') or '0'))
    except (InvalidOperation, ValueError):
        anciennete_projection = Decimal('0')

    for poste in postes_qs.order_by('ordre_affichage', 'nom_poste'):
        grilles_par_stade = {
            str(g.stade_id): g
            for g in _scoped_grilles_autonomie(request).filter(poste=poste).exclude(statut='rejetee')
        }

        points = []
        salaire_precedent = None
        for stade in stades:
            grille = grilles_par_stade.get(str(stade.id))
            employes_point = employes_par_cle.get((str(poste.id), str(stade.id)), []) if inclure_employes else []
            if grille is None:
                points.append({
                    'stade_id': str(stade.id),
                    'stade_nom': stade.nom_stade,
                    'ordre': stade.ordre,
                    'grille_id': None,
                    'salaire_net_fixe': None,
                    'prime_cible': None,
                    'prime_maximale': None,
                    'remuneration_cible': None,
                    'remuneration_maximale': None,
                    'statut': None,
                    'evolution_ariary_vs_precedent': None,
                    'evolution_pct_vs_precedent': None,
                    'anciennete_activee': False,
                    'anciennete_eligible': False,
                    'net_effectif_projete': None,
                    'majoration_anciennete_projete': None,
                    'employes': employes_point,
                })
                continue

            salaire_fixe = float(grille.salaire_net_fixe)
            evolution_ariary = None
            evolution_pct = None
            if salaire_precedent is not None:
                evolution_ariary = salaire_fixe - salaire_precedent
                evolution_pct = (evolution_ariary / salaire_precedent * 100) if salaire_precedent else None

            # Projection anciennete : uniquement pour les stades >= pivot dont la
            # majoration est activee, et si une projection en annees est demandee.
            stade_eligible_anciennete = (
                pivot_ordre is not None and stade.ordre >= pivot_ordre and grille.anciennete_activee
            )
            net_effectif_projete = None
            majoration_anciennete_projete = None
            if stade_eligible_anciennete and anciennete_projection > 0:
                net_eff = grille.net_effectif(anciennete_projection, config)
                net_effectif_projete = float(net_eff)
                majoration_anciennete_projete = float(net_eff - grille.salaire_net_fixe)

            points.append({
                'stade_id': str(stade.id),
                'stade_nom': stade.nom_stade,
                'ordre': stade.ordre,
                'grille_id': str(grille.id),
                'salaire_net_fixe': salaire_fixe,
                'prime_cible': float(grille.prime_cible),
                'prime_maximale': float(grille.prime_maximale),
                'remuneration_cible': float(grille.remuneration_cible),
                'remuneration_maximale': float(grille.remuneration_maximale),
                'statut': grille.statut,
                'evolution_ariary_vs_precedent': evolution_ariary,
                'evolution_pct_vs_precedent': evolution_pct,
                'anciennete_activee': grille.anciennete_activee,
                'anciennete_eligible': stade_eligible_anciennete,
                'net_effectif_projete': net_effectif_projete,
                'majoration_anciennete_projete': majoration_anciennete_projete,
                'employes': employes_point,
            })
            salaire_precedent = salaire_fixe

        resultat.append({
            'poste_id': str(poste.id),
            'poste_nom': poste.nom_poste,
            'categorie_professionnelle': poste.get_categorie_professionnelle_display() if poste.categorie_professionnelle else None,
            'competences_attributions': poste.competences_attributions or None,
            'type_poste': poste.type_poste,
            'niveau_poste': poste.niveau_poste,
            'points': points,
        })

    return JsonResponse({
        'success': True,
        'postes': resultat,
        'pivot_stade_ordre': pivot_ordre,
        'anciennete_projection': float(anciennete_projection),
    })


@login_required
def api_positionnement_employes(request):
    """
    Cartographie des employes sur la grille par autonomie: pour chaque employe,
    estime le stade le plus proche de son salaire net reellement paye (parmi les
    grilles appliquees de son poste), et compare avec le stade officiellement
    declare (evalue). Utilise pour la vue tableau "Positionnement des employes".
    """
    denied = _require_admin_json(request)
    if denied:
        return denied

    poste_id = request.GET.get('poste_id')
    employes_par_cle = _positionner_employes_par_stade(request)

    lignes = []
    for (cle_poste_id, cle_stade_id), employes in employes_par_cle.items():
        if poste_id and cle_poste_id != poste_id:
            continue
        lignes.extend(employes)

    lignes.sort(key=lambda e: (e['nom_affichage'] or '').lower())
    return JsonResponse({'success': True, 'employes': lignes})


@login_required
def api_graphique_save(request):
    """
    Sauvegarde partielle depuis le graphique (drag ou clic). Si la grille visee
    est deja appliquee, cree une nouvelle version en brouillon (version_precedente)
    au lieu de modifier l'appliquee.
    """
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        grille = get_object_or_404(_scoped_grilles_autonomie(request), id=data['grille_id'])
        employe = getattr(request.user, 'employe', None)

        if grille.statut == 'appliquee':
            nouvelle = GrilleAutonomie(
                poste=grille.poste,
                stade=grille.stade,
                organisation=grille.organisation,
                salaire_net_fixe=grille.salaire_net_fixe,
                prime_cible=grille.prime_cible,
                prime_maximale=grille.prime_maximale,
                date_debut_validite=date.today(),
                statut='brouillon',
                version_precedente=grille,
                createur=employe,
                anciennete_activee=grille.anciennete_activee,
                anciennete_taux_annuel_pct=grille.anciennete_taux_annuel_pct,
                anciennete_mode_capitalisation=grille.anciennete_mode_capitalisation,
                anciennete_seuil_annees=grille.anciennete_seuil_annees,
                anciennete_plafond_annees=grille.anciennete_plafond_annees,
                anciennete_plafond_majoration_pct=grille.anciennete_plafond_majoration_pct,
            )
            grille = nouvelle

        if 'salaire_net_fixe' in data:
            grille.salaire_net_fixe = _parse_decimal(data['salaire_net_fixe'], allow_none=False)
        if 'prime_cible' in data:
            grille.prime_cible = _parse_decimal(data['prime_cible']) or Decimal('0')
        if 'prime_maximale' in data:
            grille.prime_maximale = _parse_decimal(data['prime_maximale']) or Decimal('0')
        _apply_anciennete_payload(grille, data)

        grille.full_clean()
        grille.save()
        return JsonResponse({'success': True, 'grille': _serialize_grille_autonomie(grille)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except KeyError as exc:
        return JsonResponse({'success': False, 'error': f'Champ obligatoire manquant: {exc}'}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ============================================================
# CRUD Regles de primes (avec indicateurs et paliers imbriques)
# ============================================================

@login_required
def api_regles_primes_list(request):
    denied = _require_admin_json(request)
    if denied:
        return denied

    queryset = _scoped_regles_primes(request).prefetch_related('indicateurs__paliers')
    poste_id = request.GET.get('poste_id')
    if poste_id:
        queryset = queryset.filter(poste_id=poste_id)

    return JsonResponse({'success': True, 'regles': [_serialize_regle_prime(r) for r in queryset]})


def _apply_regle_payload(regle, data):
    regle.nom_regle = data.get('nom_regle', regle.nom_regle or '').strip()
    regle.type_calcul = data.get('type_calcul', regle.type_calcul)
    regle.montant_fixe = _parse_decimal(data.get('montant_fixe'))
    regle.pourcentage_salaire = _parse_decimal(data.get('pourcentage_salaire'))
    regle.periodicite = data.get('periodicite', regle.periodicite)
    regle.plafond = _parse_decimal(data.get('plafond'))
    regle.actif = data.get('actif', True)
    regle.date_debut_validite = _parse_date(data.get('date_debut_validite')) or date.today()
    regle.date_fin_validite = _parse_date(data.get('date_fin_validite'))


@login_required
def api_regles_primes_create(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        organisation = _get_request_organisation(request)
        poste = get_object_or_404(_scoped_postes_autonomie(request), id=data['poste_id'])
        stade = None
        if data.get('stade_id'):
            stade = get_object_or_404(_scoped_stades(request), id=data['stade_id'])
        employe = getattr(request.user, 'employe', None)

        with transaction.atomic():
            regle = RegleDePrime(poste=poste, stade=stade, organisation=organisation, statut='brouillon', createur=employe)
            _apply_regle_payload(regle, data)
            regle.full_clean()
            regle.save()

            for idx, ind_data in enumerate(data.get('indicateurs', [])):
                indicateur = IndicateurPrime.objects.create(
                    regle=regle,
                    nom_indicateur=ind_data.get('nom_indicateur', '').strip(),
                    unite=ind_data.get('unite', ''),
                    ponderation=_parse_decimal(ind_data.get('ponderation'), allow_none=False),
                    objectif=_parse_decimal(ind_data.get('objectif'), allow_none=False),
                    seuil_minimum=_parse_decimal(ind_data.get('seuil_minimum')),
                    ordre=ind_data.get('ordre', idx),
                )
                for palier_data in ind_data.get('paliers', []):
                    palier = PalierPrime(
                        indicateur=indicateur,
                        taux_realisation_min=_parse_decimal(palier_data.get('taux_realisation_min'), allow_none=False),
                        taux_realisation_max=_parse_decimal(palier_data.get('taux_realisation_max')),
                        taux_prime=_parse_decimal(palier_data.get('taux_prime'), allow_none=False),
                    )
                    palier.full_clean()
                    palier.save()

        return JsonResponse({'success': True, 'regle': _serialize_regle_prime(regle)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except KeyError as exc:
        return JsonResponse({'success': False, 'error': f'Champ obligatoire manquant: {exc}'}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_regles_primes_update(request, regle_id):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    regle = get_object_or_404(_scoped_regles_primes(request), id=regle_id)

    try:
        data = json.loads(request.body)
        with transaction.atomic():
            _apply_regle_payload(regle, data)
            regle.full_clean()
            regle.save()

            if 'indicateurs' in data:
                regle.indicateurs.all().delete()
                for idx, ind_data in enumerate(data.get('indicateurs', [])):
                    indicateur = IndicateurPrime.objects.create(
                        regle=regle,
                        nom_indicateur=ind_data.get('nom_indicateur', '').strip(),
                        unite=ind_data.get('unite', ''),
                        ponderation=_parse_decimal(ind_data.get('ponderation'), allow_none=False),
                        objectif=_parse_decimal(ind_data.get('objectif'), allow_none=False),
                        seuil_minimum=_parse_decimal(ind_data.get('seuil_minimum')),
                        ordre=ind_data.get('ordre', idx),
                    )
                    for palier_data in ind_data.get('paliers', []):
                        palier = PalierPrime(
                            indicateur=indicateur,
                            taux_realisation_min=_parse_decimal(palier_data.get('taux_realisation_min'), allow_none=False),
                            taux_realisation_max=_parse_decimal(palier_data.get('taux_realisation_max')),
                            taux_prime=_parse_decimal(palier_data.get('taux_prime'), allow_none=False),
                        )
                        palier.full_clean()
                        palier.save()

        return JsonResponse({'success': True, 'regle': _serialize_regle_prime(regle)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_regles_primes_delete(request, regle_id):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    regle = get_object_or_404(_scoped_regles_primes(request), id=regle_id)
    regle.delete()
    return JsonResponse({'success': True})


def _regle_workflow_action(request, regle_id, action):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    regle = get_object_or_404(_scoped_regles_primes(request), id=regle_id)
    employe = getattr(request.user, 'employe', None)

    try:
        data = json.loads(request.body) if request.body else {}
        commentaire = data.get('commentaire', '')

        if action == 'soumettre':
            regle.soumettre()
        elif action == 'valider':
            regle.valider(employe, commentaire)
        elif action == 'rejeter':
            regle.rejeter(employe, commentaire)

        return JsonResponse({'success': True, 'regle': _serialize_regle_prime(regle)})
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_regles_primes_soumettre(request, regle_id):
    return _regle_workflow_action(request, regle_id, 'soumettre')


@login_required
def api_regles_primes_valider(request, regle_id):
    return _regle_workflow_action(request, regle_id, 'valider')


@login_required
def api_regles_primes_rejeter(request, regle_id):
    return _regle_workflow_action(request, regle_id, 'rejeter')


# ============================================================
# CRUD Majorations territoriales
# ============================================================

@login_required
def api_majorations_list(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    majorations = _scoped_majorations(request)
    return JsonResponse({'success': True, 'majorations': [_serialize_majoration(m) for m in majorations]})


@login_required
def api_majorations_create(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        organisation = _get_request_organisation(request)
        from apps.geography.models import District
        from apps.organization.models import Compte

        district = District.objects.filter(id=data['district_id']).first() if data.get('district_id') else None
        base = _scoped_bases_majorations(request).filter(id=data['base_id']).first() if data.get('base_id') else None
        if data.get('district_id') and district is None:
            raise ValidationError({'district_id': "District introuvable."})
        if data.get('base_id') and base is None:
            raise ValidationError({'base_id': "Base introuvable ou inaccessible."})

        majoration = MajorationTerritoriale(
            organisation=organisation,
            nom=data.get('nom', '').strip(),
            district=district,
            base=base,
            type_montant=data.get('type_montant'),
            montant_fixe=_parse_decimal(data.get('montant_fixe')),
            pourcentage_salaire=_parse_decimal(data.get('pourcentage_salaire')),
            compte=Compte.objects.filter(id=data['compte_id']).first() if data.get('compte_id') else None,
            actif=data.get('actif', True),
            date_debut_validite=_parse_date(data.get('date_debut_validite')) or date.today(),
            date_fin_validite=_parse_date(data.get('date_fin_validite')),
        )
        majoration.full_clean()
        majoration.save()
        return JsonResponse({'success': True, 'majoration': _serialize_majoration(majoration)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_majorations_update(request, majoration_id):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    majoration = get_object_or_404(_scoped_majorations(request), id=majoration_id)
    try:
        data = json.loads(request.body)
        from apps.geography.models import District
        from apps.organization.models import Compte

        if 'nom' in data:
            majoration.nom = data['nom'].strip()
        if 'district_id' in data:
            majoration.district = District.objects.filter(id=data['district_id']).first() if data['district_id'] else None
            if data['district_id'] and majoration.district is None:
                raise ValidationError({'district_id': "District introuvable."})
        if 'base_id' in data:
            majoration.base = _scoped_bases_majorations(request).filter(id=data['base_id']).first() if data['base_id'] else None
            if data['base_id'] and majoration.base is None:
                raise ValidationError({'base_id': "Base introuvable ou inaccessible."})
        if 'type_montant' in data:
            majoration.type_montant = data['type_montant']
        if 'montant_fixe' in data:
            majoration.montant_fixe = _parse_decimal(data['montant_fixe'])
        if 'pourcentage_salaire' in data:
            majoration.pourcentage_salaire = _parse_decimal(data['pourcentage_salaire'])
        if 'compte_id' in data:
            majoration.compte = Compte.objects.filter(id=data['compte_id']).first() if data['compte_id'] else None
        if 'actif' in data:
            majoration.actif = data['actif']
        if 'date_debut_validite' in data:
            majoration.date_debut_validite = _parse_date(data['date_debut_validite']) or majoration.date_debut_validite
        if 'date_fin_validite' in data:
            majoration.date_fin_validite = _parse_date(data['date_fin_validite'])

        majoration.full_clean()
        majoration.save()
        return JsonResponse({'success': True, 'majoration': _serialize_majoration(majoration)})
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_majorations_delete(request, majoration_id):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    majoration = get_object_or_404(_scoped_majorations(request), id=majoration_id)
    majoration.delete()
    return JsonResponse({'success': True})


# ============================================================
# Controles de coherence
# ============================================================

@login_required
def api_controles_coherence(request):
    denied = _require_admin_json(request)
    if denied:
        return denied

    organisation = _get_request_organisation(request)
    poste_id = request.GET.get('poste_id')
    poste = None
    if poste_id:
        poste = get_object_or_404(_scoped_postes_autonomie(request), id=poste_id)

    alertes = calculer_alertes_coherence(organisation=organisation, poste=poste)
    return JsonResponse({'success': True, 'alertes': alertes})


# ============================================================
# Simulateur de remuneration
# ============================================================

@login_required
def api_simulateur_donnees_employe(request, employe_id):
    denied = _require_admin_json(request)
    if denied:
        return denied

    employe = get_object_or_404(_scoped_employes_simulateur(request), id=employe_id)

    nombre_points_eau = employe.ouvrages_responsable.filter(date_fin__isnull=True).count()

    resultats_existants = []
    if employe.poste_id and employe.stade_autonomie_actuel_id:
        regles = RegleDePrime.objects.filter(
            poste=employe.poste, actif=True, statut='appliquee',
        ).filter(models.Q(stade=employe.stade_autonomie_actuel) | models.Q(stade__isnull=True)).prefetch_related('indicateurs')
        for regle in regles:
            for indicateur in regle.indicateurs.all():
                dernier = ResultatIndicateur.objects.filter(employe=employe, indicateur=indicateur).order_by('-periode_fin').first()
                resultats_existants.append({
                    'indicateur_id': str(indicateur.id),
                    'nom_indicateur': indicateur.nom_indicateur,
                    'unite': indicateur.unite,
                    'objectif': float(indicateur.objectif),
                    'derniere_valeur_realisee': float(dernier.valeur_realisee) if dernier else None,
                })

    return JsonResponse({
        'success': True,
        'employe': {
            'id': str(employe.id),
            'surnom': employe.surnom or '',
            'nom_affichage': employe.nom_affichage,
            'poste_id': str(employe.poste_id) if employe.poste_id else None,
            'poste_nom': employe.poste.nom_poste if employe.poste_id else None,
            'stade_id': str(employe.stade_autonomie_actuel_id) if employe.stade_autonomie_actuel_id else None,
            'stade_nom': employe.stade_autonomie_actuel.nom_stade if employe.stade_autonomie_actuel_id else None,
            'stade_ordre': employe.stade_autonomie_actuel.ordre if employe.stade_autonomie_actuel_id else None,
            'base_id': str(employe.base_id) if employe.base_id else None,
            'date_debut_anciennete_autonomie': (
                employe.date_debut_anciennete_autonomie.isoformat()
                if employe.date_debut_anciennete_autonomie else None
            ),
            'anciennete_autonomie_annees': float(employe.anciennete_autonomie_annees()),
        },
        'pivot_stade_ordre': _pivot_stade_ordre(request),
        'nombre_points_eau_couverts': nombre_points_eau,
        'resultats_existants': resultats_existants,
    })


def _calculer_simulation(employe, distance_annuelle_km, nombre_points_eau_couverts, resultats_override):
    config = ConfigSalaire.get_config()
    grille = GrilleAutonomie.get_grille_for_poste_and_stade(employe.poste, employe.stade_autonomie_actuel)

    salaire_socle = grille.salaire_net_fixe if grille else Decimal('0')
    anciennete_annees = employe.anciennete_autonomie_annees()
    date_debut_anciennete = employe.date_debut_anciennete_autonomie
    if grille is not None:
        salaire_garanti = grille.net_effectif(anciennete_annees, config)
    else:
        salaire_garanti = Decimal('0')
    majoration_anciennete_montant = salaire_garanti - salaire_socle

    primes = calculer_toutes_primes_employe(employe, resultats_override=resultats_override)
    total_primes = sum((p['montant_prime'] for p in primes), Decimal('0'))

    majoration = MajorationTerritoriale.objects.filter(base=employe.base, actif=True).first()
    majoration_montant = Decimal('0')
    if majoration:
        if majoration.type_montant == 'montant_fixe':
            majoration_montant = majoration.montant_fixe or Decimal('0')
        else:
            majoration_montant = (majoration.pourcentage_salaire or Decimal('0')) / Decimal('100') * salaire_garanti

    remuneration_totale = salaire_garanti + total_primes + majoration_montant

    detail_primes = []
    for p in primes:
        detail_primes.append({
            'regle_id': str(p['regle'].id),
            'nom_regle': p['regle'].nom_regle,
            'montant_prime': float(p['montant_prime']),
            'plafonne': p['plafonne'],
            'details_indicateurs': [
                {
                    'indicateur_id': str(d['indicateur'].id),
                    'nom_indicateur': d['indicateur'].nom_indicateur,
                    'valeur_realisee': float(d['valeur_realisee']) if d['valeur_realisee'] is not None else None,
                    'taux_realisation_pct': float(d['taux_realisation_pct']) if d['taux_realisation_pct'] is not None else None,
                    'sous_seuil': d['sous_seuil'],
                    'montant_part_indicateur': float(d['montant_part_indicateur']),
                }
                for d in p['details_indicateurs']
            ],
        })

    return {
        'salaire_garanti': salaire_garanti,
        'salaire_socle': salaire_socle,
        'majoration_anciennete_montant': majoration_anciennete_montant,
        'anciennete_autonomie_annees': float(anciennete_annees),
        'date_debut_anciennete': date_debut_anciennete.isoformat() if date_debut_anciennete else None,
        'total_primes_resultat': total_primes,
        'majoration_territoriale_montant': majoration_montant,
        'majoration_territoriale_nom': majoration.nom if majoration else None,
        'remuneration_nette_totale': remuneration_totale,
        'detail_primes': detail_primes,
    }


@login_required
def api_simulateur_calculer(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        employe = get_object_or_404(_scoped_employes_simulateur(request), id=data['employe_id'])
        distance_annuelle_km = _parse_decimal(data.get('distance_annuelle_km'))
        nombre_points_eau_couverts = data.get('nombre_points_eau_couverts')
        resultats_override = data.get('resultats_indicateurs', {})  # {indicateur_id: valeur}

        resultat = _calculer_simulation(employe, distance_annuelle_km, nombre_points_eau_couverts, resultats_override)

        alertes = calculer_alertes_coherence(organisation=_get_request_organisation(request), poste=employe.poste)
        alertes_pertinentes = [a for a in alertes if a.get('poste_id') == str(employe.poste_id)]

        return JsonResponse({
            'success': True,
            'salaire_garanti': float(resultat['salaire_garanti']),
            'salaire_socle': float(resultat['salaire_socle']),
            'majoration_anciennete_montant': float(resultat['majoration_anciennete_montant']),
            'anciennete_autonomie_annees': resultat['anciennete_autonomie_annees'],
            'date_debut_anciennete': resultat['date_debut_anciennete'],
            'total_primes_resultat': float(resultat['total_primes_resultat']),
            'majoration_territoriale_montant': float(resultat['majoration_territoriale_montant']),
            'majoration_territoriale_nom': resultat['majoration_territoriale_nom'],
            'remuneration_nette_totale': float(resultat['remuneration_nette_totale']),
            'detail_primes': resultat['detail_primes'],
            'alertes': alertes_pertinentes,
        })
    except KeyError as exc:
        return JsonResponse({'success': False, 'error': f'Champ obligatoire manquant: {exc}'}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_simulateur_sauvegarder(request):
    denied = _require_admin_json(request)
    if denied:
        return denied
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body)
        employe = get_object_or_404(_scoped_employes_simulateur(request), id=data['employe_id'])
        distance_annuelle_km = _parse_decimal(data.get('distance_annuelle_km'))
        nombre_points_eau_couverts = data.get('nombre_points_eau_couverts')
        resultats_override = data.get('resultats_indicateurs', {})
        createur = getattr(request.user, 'employe', None)

        resultat = _calculer_simulation(employe, distance_annuelle_km, nombre_points_eau_couverts, resultats_override)

        simulation = SimulationRemuneration.objects.create(
            employe=employe,
            poste=employe.poste,
            stade=employe.stade_autonomie_actuel,
            distance_annuelle_km=distance_annuelle_km,
            nombre_points_eau_couverts=nombre_points_eau_couverts,
            salaire_garanti=resultat['salaire_garanti'],
            total_primes_resultat=resultat['total_primes_resultat'],
            majoration_territoriale_montant=resultat['majoration_territoriale_montant'],
            remuneration_nette_totale=resultat['remuneration_nette_totale'],
            detail_calcul_json={
                'detail_primes': resultat['detail_primes'],
                'majoration_territoriale_nom': resultat['majoration_territoriale_nom'],
                'salaire_socle': float(resultat['salaire_socle']),
                'majoration_anciennete_montant': float(resultat['majoration_anciennete_montant']),
                'anciennete_autonomie_annees': resultat['anciennete_autonomie_annees'],
                'date_debut_anciennete': resultat['date_debut_anciennete'],
            },
            cree_par=createur,
        )

        return JsonResponse({'success': True, 'simulation_id': str(simulation.id)})
    except KeyError as exc:
        return JsonResponse({'success': False, 'error': f'Champ obligatoire manquant: {exc}'}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)
