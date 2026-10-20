"""Page et APIs de gestion des coûts types par activité (réparation, installation, réhabilitation)."""
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.billing.models import TypePointEau
from apps.employees.models import FichePoste
from apps.employees.permissions import employe_required, is_directeur_poste
from apps.billing.models import PointEau
from apps.infrastructure.models import EquipementConstitutif, TypeEquipement
from apps.inspections.models import ComposantTypeEquipement, ComposantTypePointEau
from apps.planning.couts_types import (
    appliquer_couts_types,
    fusionner_lignes,
    trouver_couts_types,
    trouver_couts_types_cible,
)
from apps.planning.couts_types_historique import (
    LIMITE_INTERVENTIONS,
    NIVEAU_AUTO,
    NIVEAUX,
    agreger_historique,
    interventions_historiques,
)
from apps.planning.models import Designation, Planning
from apps.planning.models_couts_types import CoutTypeActivite, CoutTypeLigne
from apps.planning.couts_types_checklist import (
    FAMILLES,
    STATUT_A_REMPLIR,
    STATUT_REMPLI,
    STATUT_VIDE,
    assembler_checklist,
    cle_combinaison,
    combinaisons_theoriques,
    famille_fiche,
    observer_combinaisons,
    referentiel,
)
from apps.planning.repair_classification import get_reparations_fiches_queryset


def _peut_modifier(request):
    return request.user.is_staff or is_directeur_poste(request.user)


def _decimal(valeur, defaut=None):
    if valeur in (None, ''):
        return defaut
    try:
        return Decimal(str(valeur).replace(',', '.'))
    except InvalidOperation:
        raise ValidationError(f"Nombre invalide : {valeur}")


def _cle_bareme(ct):
    """Clé de check-list d'un barème existant."""
    if ct.type_equipement_id:
        return cle_combinaison(ct.fiche_poste_id, 'equipement', ct.type_equipement_id, ct.composant_equipement_id)
    return cle_combinaison(ct.fiche_poste_id, 'point_eau', ct.type_point_eau_id, ct.composant_point_eau_id)


def _statistiques(ligne):
    """Champs communs de check-list issus de assembler_checklist."""
    return {
        'cle': '|'.join(x or '' for x in ligne['cle']),
        'statut': ligne['statut'],
        'observee': ligne['observee'],
        'theorique': not ligne['observee'] and ligne['statut'] == STATUT_A_REMPLIR,
        'nb_historique': ligne['nb_historique'],
        'nb_chiffrees': ligne['nb_chiffrees'],
        'reel_moyen': ligne['reel_moyen'],
        'nb_reel': ligne['nb_chiffrees'],
    }


def _serialiser(ct, ligne):
    composant = ct.composant
    type_cible = ct.type_equipement or ct.type_point_eau
    return {
        'id': str(ct.id),
        'fiche_id': str(ct.fiche_poste_id),
        'activite': ct.fiche_poste.tache,
        'famille': famille_fiche(ct.fiche_poste),
        'cible_genre': ct.cible_genre,
        'type_cible_id': str(type_cible.id) if type_cible else '',
        'type_cible': getattr(type_cible, 'nom_type', ''),
        'composant_id': str(composant.id) if composant else '',
        'composant': composant.nom_composant if composant else '',
        'notes': ct.notes,
        'actif': ct.actif,
        'total_estime': float(ct.total_estime),
        'lignes': [{
            'designation_id': str(l.designation_id),
            'designation': l.designation.nom,
            'type_designation': l.designation.type_designation.nom,
            'unite': l.designation.unite or '',
            'quantite': float(l.quantite),
            'pu': float(l.pu_effectif),
            'pu_surcharge': l.pu is not None,
            'montant': float(l.montant),
        } for l in ct.lignes.all()],
        **_statistiques(ligne),
    }


def _serialiser_a_remplir(ligne, ref):
    """Ligne de check-list sans barème (combinaison à renseigner)."""
    fiche_id, genre, type_id, composant_id = ligne['cle']
    fiche = ref['fiches'].get(fiche_id)
    nom_type = ref['types'][genre].get(type_id)
    if fiche is None or nom_type is None:
        return None   # activité, type ou composant qui n'existe plus ou hors périmètre
    nom_composant = ref['composants'][genre].get(composant_id) if composant_id else ''
    if composant_id and nom_composant is None:
        return None
    return {
        'id': '',
        'fiche_id': fiche_id,
        'activite': fiche['nom'],
        'famille': fiche['famille'],
        'cible_genre': genre,
        'type_cible_id': type_id,
        'type_cible': nom_type,
        'composant_id': composant_id or '',
        'composant': nom_composant or '',
        'notes': '',
        'actif': True,
        'total_estime': 0,
        'lignes': [],
        **_statistiques(ligne),
    }


def contexte_page(request):
    """Données de référence de la page des coûts types (servie par le sous-domaine ouvrages)."""
    fiches = [
        {'id': str(f.id), 'nom': f.tache, 'famille': famille_fiche(f)}
        for f in get_reparations_fiches_queryset().order_by('tache')
    ]
    contexte = {
        'fiches': fiches,
        'familles': FAMILLES,
        'types_equipement': list(TypeEquipement.objects.order_by('nom_type').values('id', 'nom_type')),
        'types_point_eau': list(TypePointEau.objects.order_by('nom_type').values('id', 'nom_type')),
        'composants_equipement': [
            {'id': str(c.id), 'nom': c.nom_composant, 'type_id': str(c.type_equipement_id)}
            for c in ComposantTypeEquipement.objects.order_by('ordre_affichage', 'nom_composant')
        ],
        'composants_point_eau': [
            {'id': str(c.id), 'nom': c.nom_composant, 'type_id': str(c.type_point_eau_id)}
            for c in ComposantTypePointEau.objects.order_by('ordre_affichage', 'nom_composant')
        ],
        'designations': [
            {'id': str(d.id), 'nom': d.nom, 'type': d.type_designation.nom, 'unite': d.unite or '',
             'pu': float(d.prix_unitaire or 0)}
            for d in Designation.objects.filter(actif=True).select_related('type_designation')
        ],
        'peut_modifier': _peut_modifier(request),
    }
    return contexte


@employe_required
@require_GET
def api_couts_types_liste(request):
    """
    Check-list des coûts types : barèmes existants + combinaisons à renseigner.

    Par défaut, les combinaisons « possibles » sont celles déjà rencontrées dans les plannings
    passés ; theoriques=1 ajoute toutes celles que permettent les règles des activités.
    """
    qs = (CoutTypeActivite.objects
          .select_related('fiche_poste__type_activites', 'type_equipement', 'type_point_eau',
                          'composant_equipement', 'composant_point_eau')
          .prefetch_related('lignes__designation__type_designation'))
    couts_types = list(qs)
    par_id = {str(ct.id): ct for ct in couts_types}
    ref = referentiel()

    bareme_par_cle = {_cle_bareme(ct): {'id': str(ct.id), 'nb_lignes': len(ct.lignes.all())}
                      for ct in couts_types}
    fiche_ids = set(ref['fiches']) | {str(ct.fiche_poste_id) for ct in couts_types}
    theoriques = ()
    if request.GET.get('theoriques') == '1':
        theoriques = combinaisons_theoriques([f['objet'] for f in ref['fiches'].values()])
    lignes = assembler_checklist(observer_combinaisons(fiche_ids), bareme_par_cle, theoriques)

    donnees = []
    for ligne in lignes:
        if ligne['cout_type_id']:
            donnees.append(_serialiser(par_id[ligne['cout_type_id']], ligne))
        else:
            element = _serialiser_a_remplir(ligne, ref)
            if element:
                donnees.append(element)

    famille = request.GET.get('famille', '')
    if famille:
        donnees = [d for d in donnees if d['famille'] == famille]
    # Par activité, les combinaisons les plus fréquentes dans l'historique d'abord.
    donnees.sort(key=lambda d: (d['famille'], d['activite'], -d['nb_chiffrees'],
                                d['cible_genre'], d['type_cible'], d['composant']))
    comptes = {s: sum(1 for d in donnees if d['statut'] == s)
               for s in (STATUT_REMPLI, STATUT_VIDE, STATUT_A_REMPLIR)}
    return JsonResponse({'success': True, 'couts_types': donnees, 'comptes': comptes})


@employe_required
@require_POST
def api_cout_type_sauvegarder(request):
    if not _peut_modifier(request):
        return JsonResponse({'success': False, 'error': "Réservé à la direction"}, status=403)
    try:
        data = json.loads(request.body or '{}')
        with transaction.atomic():
            ct = (get_object_or_404(CoutTypeActivite, pk=data['id']) if data.get('id')
                  else CoutTypeActivite())
            ct.fiche_poste = get_object_or_404(FichePoste, pk=data.get('fiche_id'))
            genre = data.get('cible_genre')
            ct.type_equipement_id = data.get('type_cible_id') or None if genre == 'equipement' else None
            ct.type_point_eau_id = data.get('type_cible_id') or None if genre == 'point_eau' else None
            composant_id = data.get('composant_id') or None
            ct.composant_equipement_id = composant_id if genre == 'equipement' else None
            ct.composant_point_eau_id = composant_id if genre == 'point_eau' else None
            ct.notes = data.get('notes', '')
            ct.actif = bool(data.get('actif', True))
            ct.full_clean(exclude=['fiche_poste'])
            ct.save()

            ct.lignes.all().delete()
            vues = set()
            for ordre, ligne in enumerate(data.get('lignes', [])):
                designation = get_object_or_404(Designation, pk=ligne['designation_id'])
                if designation.id in vues:
                    raise ValidationError(f"Désignation en double : {designation.nom}")
                vues.add(designation.id)
                quantite = _decimal(ligne.get('quantite'), Decimal('1'))
                if quantite <= 0:
                    raise ValidationError(f"Quantité invalide pour {designation.nom}")
                CoutTypeLigne.objects.create(
                    cout_type=ct, designation=designation, quantite=quantite,
                    pu=_decimal(ligne.get('pu')), ordre=ordre,
                )
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': ' '.join(exc.messages)}, status=400)
    except (KeyError, ValueError):
        return JsonResponse({'success': False, 'error': "Données invalides"}, status=400)
    return JsonResponse({'success': True, 'id': str(ct.id)})


@employe_required
@require_POST
def api_cout_type_supprimer(request, cout_type_id):
    if not _peut_modifier(request):
        return JsonResponse({'success': False, 'error': "Réservé à la direction"}, status=403)
    get_object_or_404(CoutTypeActivite, pk=cout_type_id).delete()
    return JsonResponse({'success': True})


@employe_required
@require_POST
def api_planning_appliquer_cout_type(request, planning_id):
    """Pré-remplit les détails d'un planning avec le coût type de son activité / cible / composants."""
    planning = get_object_or_404(
        Planning.objects.select_related('cible_equipement', 'cible_point_eau'), pk=planning_id)
    try:
        remplacer = bool(json.loads(request.body or '{}').get('remplacer'))
    except ValueError:
        remplacer = False
    if not trouver_couts_types(planning):
        return JsonResponse({
            'success': False,
            'error': "Aucun coût type pour cette activité, cette cible et ces composants",
        }, status=404)
    creees, deja_presentes, non_reprises = appliquer_couts_types(planning, remplacer=remplacer)
    return JsonResponse({
        'success': True,
        'nb_creees': len(creees),
        'montant': float(sum(d.montant for d in creees)),
        'deja_presentes': [d.nom for d in deja_presentes],
        'non_reprises': [d.nom for d in non_reprises],
    })


@employe_required
@require_GET
def api_cout_type_apercu(request):
    """
    Aperçu du coût type pour le formulaire de réparation (aucune écriture).

    Paramètres : fiche_id, equipement_id OU point_eau_id, composants_ids (séparés par des virgules).
    Les lignes sont réparties comme dans le formulaire : « avances » et « bons de livraison » ;
    les autres désignations ne peuvent pas y être saisies et sont signalées.
    """
    get = request.GET.get
    equipement = EquipementConstitutif.objects.filter(pk=get('equipement_id')).first() if get('equipement_id') else None
    point_eau = (None if equipement else
                 PointEau.objects.filter(pk=get('point_eau_id')).first() if get('point_eau_id') else None)
    composant_ids = [c for c in (get('composants_ids') or '').split(',') if c]
    if equipement:
        composants = list(ComposantTypeEquipement.objects.filter(pk__in=composant_ids))
    else:
        composants = list(ComposantTypePointEau.objects.filter(pk__in=composant_ids))

    couts_types = trouver_couts_types_cible(get('fiche_id'), equipement, point_eau, composants)
    if not couts_types:
        return JsonResponse({'success': True, 'trouve': False, 'avances': [], 'bons': [], 'ignorees': []})

    avances, bons, ignorees = [], [], []
    for ligne in fusionner_lignes(couts_types):
        designation = ligne['designation']
        type_avance = (designation.type_avance_caissiere or '').lower()
        element = {
            'designation_id': str(designation.id),
            'designation_nom': designation.nom,
            'quantity': float(ligne['quantite']),
            'quantite': float(ligne['quantite']),
            'pu': float(ligne['pu']),
        }
        if 'avance' in type_avance:
            avances.append(element)
        elif 'bon' in type_avance or 'livraison' in type_avance:
            bons.append(element)
        else:
            ignorees.append(designation.nom)
    return JsonResponse({
        'success': True,
        'trouve': True,
        'avances': avances,
        'bons': bons,
        'ignorees': ignorees,
        'total_estime': float(sum(Decimal(str(e['quantity'])) * Decimal(str(e['pu'])) for e in avances + bons)),
    })


@employe_required
@require_GET
def api_cout_type_historique(request):
    """
    Historique souple des interventions passées, pour aider à remplir un barème.

    Paramètres : fiche_id, cible_genre (equipement | point_eau), type_cible_id,
    composant_id (optionnel), niveau (auto | composant | souple | type | activite).
    Les composants étant rarement renseignés dans les anciens plannings, le mode auto
    élargit la sélection tant qu'il y a trop peu d'interventions chiffrées.
    """
    get = request.GET
    niveau = get.get('niveau') or NIVEAU_AUTO
    if niveau not in (NIVEAU_AUTO,) + NIVEAUX:
        niveau = NIVEAU_AUTO
    interventions, niveau_utilise = interventions_historiques(
        get.get('fiche_id'), get.get('cible_genre'), get.get('type_cible_id'),
        get.get('composant_id') or None, niveau)
    resume = agreger_historique(interventions)
    resume['interventions'] = [i for i in interventions if i['lignes']][:LIMITE_INTERVENTIONS]
    resume['niveau_demande'] = niveau
    resume['niveau_utilise'] = niveau_utilise
    resume['success'] = True
    return JsonResponse(resume)
