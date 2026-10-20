"""
API mobile — module Réunions/Représentantes des usagers (app Android `HydriaReunions`).

Montée sous /api/mobile/v1/reunions/. Réutilise le jeton `scope='mobile'` émis
par /mobile/api/login/ (même décorateur que les endpoints terrain/compta, cf.
apps/accounting/mobile_api_v1.py qui sert le même rôle pour HydriaCompta).

V1 — décisions arrêtées :
- Périmètre représentantes/avis : villages accessibles à l'utilisateur, mêmes
  helpers que la page web usagers/representants/ (_filter_representants_queryset_for_user,
  _filter_avis_queryset_for_user).
- Périmètre réunions/décisions/participants : aucune restriction supplémentaire
  au-delà de la connexion (comme reunions_list côté web), borné par année pour
  le bootstrap.
- Idempotence : les objets créés côté mobile portent un UUID généré par le
  client (les modèles usagers utilisent déjà des UUID en clé primaire) ; une
  mutation avec un id déjà connu est acceptée sans le recréer.
- Notes avancées : adaptateur au-dessus de `notes/` (entity_type/entity_id),
  actif seulement si settings.ENABLE_NOTES est vrai (app conditionnelle, cf.
  hydria/settings.py) — répond proprement 'NOTES_DISABLED' sinon plutôt que
  de planter.
"""
import functools
import json
import logging
import traceback
import uuid
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.auth_tokens import token_or_session_required
from apps.core.models import WidgetAuthToken

from .models import AvisRepresentant, RepresentantUsager
from .models_reunions import (
    Autorite,
    DecisionReunion,
    ParticipantReunion,
    PieceJointeReunion,
    Reunion,
    TiersParticipant,
)
from .views import _filter_avis_queryset_for_user, _filter_representants_queryset_for_user
from .views_reunions import _current_employe

logger = logging.getLogger(__name__)
mobile_required = token_or_session_required(scope=WidgetAuthToken.SCOPE_MOBILE)

BOOTSTRAP_MAX_REPRESENTANTS = 2000
BOOTSTRAP_MAX_AVIS = 2000
BOOTSTRAP_MAX_REUNIONS = 500

try:
    from notes.models import Note, NoteLink, NoteTask
    from notes.views import _accessible_notes_queryset, _replace_tags
except Exception:  # noqa: BLE001 — app notes desactivee (ENABLE_NOTES=False) ou pgvector absent
    Note = NoteLink = NoteTask = None
    _accessible_notes_queryset = _replace_tags = None


def _notes_available():
    return bool(getattr(settings, 'ENABLE_NOTES', False) and Note is not None)


def _json_errors(view):
    """Toute exception -> JSON 500 (jamais de page HTML) + trace dans les logs."""
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("reunions mobile %s a échoué", view.__name__)
            return JsonResponse(
                {'code': 'SERVER_ERROR', 'message': str(exc), 'where': view.__name__,
                 'trace': traceback.format_exc().splitlines()[-6:]},
                status=500,
            )
    return wrapper


class _RejetValidation(Exception):
    pass


def _iso(value):
    return value.isoformat() if value else None


def _capabilities():
    codes = {
        'representant.read': True, 'avis.read': True, 'avis.create': True,
        'reunion.read': True, 'reunion.create': True, 'reunion.update': True,
        'participant.create': True, 'decision.create': True, 'decision.update': True,
        'piece_jointe.create': True, 'note.read': _notes_available(), 'note.create': _notes_available(),
    }
    return [{'code': c, 'allowed': v} for c, v in codes.items()]


# --------------------------------------------------------------------------- #
#  Sérialisation
# --------------------------------------------------------------------------- #

def _representant_json(r):
    village = r.village
    commune = village.fokontany.commune if village and village.fokontany_id else None
    return {
        'id': str(r.id),
        'nom': r.nom or '',
        'contact': r.contact or '',
        'observation': r.observation or '',
        'village_id': str(r.village_id) if r.village_id else None,
        'village_nom': village.nom_village if village else '',
        'commune_id': str(commune.id) if commune else None,
        'commune_nom': commune.nom_commune if commune else '',
        'date_debut': _iso(r.date_debut),
        'date_fin': _iso(r.date_fin),
        'actif': r.actif,
        'est_actif': r.est_actif,
        'created_at': r.created_at.isoformat(),
        'updated_at': r.updated_at.isoformat(),
    }


def _avis_json(a):
    return {
        'id': str(a.id),
        'representant_id': str(a.representant_id),
        'date_avis': _iso(a.date_avis),
        'employe_id': str(a.employe_id) if a.employe_id else None,
        'reunion_id': str(a.reunion_id) if a.reunion_id else None,
        'quantite_ok': a.quantite_ok,
        'qualite_ok': a.qualite_ok,
        'delai_reparation_ok': a.delai_reparation_ok,
        'relation_gestionnaire_ok': a.relation_gestionnaire_ok,
        'probleme_technique': a.probleme_technique or '',
        'probleme_recouvrement': a.probleme_recouvrement or '',
        'probleme_regles_utilisation': a.probleme_regles_utilisation or '',
        'remarque': a.remarque or '',
        'score_satisfaction': a.score_satisfaction,
        'pourcentage_satisfaction': a.pourcentage_satisfaction,
        'est_negatif': a.est_negatif,
        'created_at': a.created_at.isoformat(),
        'updated_at': a.updated_at.isoformat(),
    }


def _reunion_json(reunion, participants=None, decisions=None, pieces=None):
    return {
        'id': str(reunion.id),
        'type_reunion': reunion.type_reunion,
        'date_reunion': _iso(reunion.date_reunion),
        'commune_id': str(reunion.commune_id) if reunion.commune_id else None,
        'district_id': str(reunion.district_id) if reunion.district_id else None,
        'region_id': str(reunion.region_id) if reunion.region_id else None,
        'lieu_affiche': reunion.lieu_affiche,
        'lieu': reunion.lieu or '',
        'objet': reunion.objet,
        'compte_rendu': reunion.compte_rendu or '',
        'recommandations': reunion.recommandations or '',
        'organise_par_id': str(reunion.organise_par_id) if reunion.organise_par_id else None,
        'nb_participants': reunion.nb_participants,
        'nb_decisions_en_cours': reunion.nb_decisions_en_cours,
        'participants': [_participant_json(p) for p in participants] if participants is not None else None,
        'decisions': [_decision_json(d) for d in decisions] if decisions is not None else None,
        'pieces_jointes': [_piece_jointe_json(p) for p in pieces] if pieces is not None else None,
        'created_at': reunion.created_at.isoformat(),
        'updated_at': reunion.updated_at.isoformat(),
    }


def _participant_json(p):
    return {
        'id': str(p.id),
        'reunion_id': str(p.reunion_id),
        'type_participant': p.type_participant,
        'nom_affiche': p.nom_affiche,
        'representant_id': str(p.representant_id) if p.representant_id else None,
        'employe_id': str(p.employe_id) if p.employe_id else None,
        'autorite_id': str(p.autorite_id) if p.autorite_id else None,
        'tiers_id': str(p.tiers_id) if p.tiers_id else None,
        'point_eau_id': str(p.point_eau_id) if p.point_eau_id else None,
        'fonction_libre': p.fonction_libre or '',
        'contact_libre': p.contact_libre or '',
        'present': p.present,
        'created_at': p.created_at.isoformat(),
    }


def _decision_json(d):
    return {
        'id': str(d.id),
        'reunion_id': str(d.reunion_id),
        'description': d.description,
        'responsable_id': str(d.responsable_id) if d.responsable_id else None,
        'date_echeance': _iso(d.date_echeance),
        'statut': d.statut,
        'date_realisation': _iso(d.date_realisation),
        'commentaire_suivi': d.commentaire_suivi or '',
        'est_en_retard': d.est_en_retard,
        'created_at': d.created_at.isoformat(),
        'updated_at': d.updated_at.isoformat(),
    }


def _piece_jointe_json(p):
    return {
        'id': str(p.id),
        'reunion_id': str(p.reunion_id),
        'type_piece': p.type_piece,
        'url': p.fichier.url if p.fichier else None,
        'legende': p.legende or '',
        'created_at': p.created_at.isoformat(),
    }


# --------------------------------------------------------------------------- #
#  bootstrap
# --------------------------------------------------------------------------- #

@require_GET
@mobile_required
@_json_errors
def bootstrap(request):
    representants_qs = _filter_representants_queryset_for_user(
        RepresentantUsager.objects.select_related('village', 'village__fokontany__commune').filter(actif=True),
        request.user,
    ).order_by('village__nom_village', 'nom')[:BOOTSTRAP_MAX_REPRESENTANTS]
    representants = [_representant_json(r) for r in representants_qs]

    avis_qs = _filter_avis_queryset_for_user(
        AvisRepresentant.objects.all(), request.user
    ).order_by('-date_avis')[:BOOTSTRAP_MAX_AVIS]
    avis = [_avis_json(a) for a in avis_qs]

    annee = timezone.localdate().year
    reunions_qs = Reunion.objects.select_related('commune', 'district', 'region', 'organise_par').filter(
        date_reunion__year__gte=annee - 1
    ).prefetch_related('participants', 'decisions', 'pieces_jointes').order_by('-date_reunion')[:BOOTSTRAP_MAX_REUNIONS]
    reunions = [
        _reunion_json(r, participants=r.participants.all(), decisions=r.decisions.all(), pieces=r.pieces_jointes.all())
        for r in reunions_qs
    ]

    autorites = [
        {'id': str(a.id), 'nom': a.nom, 'fonction': a.fonction or ''}
        for a in Autorite.objects.filter(actif=True).order_by('nom')
    ]
    tiers = [
        {'id': str(t.id), 'nom': t.nom}
        for t in TiersParticipant.objects.filter(actif=True).order_by('nom')
    ]

    employe = _current_employe(request)
    now = timezone.now().isoformat()
    return JsonResponse({
        'cursor': now,
        'server_time': now,
        'payload': {
            'user': {
                'id': str(request.user.pk),
                'username': request.user.get_username(),
                'employe_id': str(employe.id) if employe else None,
                'employe_nom': employe.nom_affichage if employe else None,
            },
            'capabilities': _capabilities(),
            'representants': representants,
            'representants_tronque': len(representants) >= BOOTSTRAP_MAX_REPRESENTANTS,
            'avis': avis,
            'avis_tronque': len(avis) >= BOOTSTRAP_MAX_AVIS,
            'reunions': reunions,
            'reunions_tronque': len(reunions) >= BOOTSTRAP_MAX_REUNIONS,
            'autorites': autorites,
            'tiers': tiers,
        },
    })


# --------------------------------------------------------------------------- #
#  changes (delta par updated_at/created_at)
# --------------------------------------------------------------------------- #

@require_GET
@mobile_required
@_json_errors
def changes(request):
    since_raw = (request.GET.get('since') or '').strip()
    try:
        since = datetime.fromisoformat(since_raw) if since_raw else None
    except ValueError:
        since = None

    if since is None:
        return JsonResponse({
            'cursor': timezone.now().isoformat(),
            'has_more': False,
            'full_refresh_required': True,
            'reason': 'MISSING_OR_INVALID_SINCE',
            'changes': {},
        })

    representants_qs = _filter_representants_queryset_for_user(
        RepresentantUsager.objects.filter(updated_at__gt=since), request.user,
    )
    avis_qs = _filter_avis_queryset_for_user(
        AvisRepresentant.objects.filter(updated_at__gt=since), request.user,
    )
    reunions_qs = Reunion.objects.filter(updated_at__gt=since)
    decisions_qs = DecisionReunion.objects.filter(updated_at__gt=since)
    participants_qs = ParticipantReunion.objects.filter(created_at__gt=since)
    pieces_qs = PieceJointeReunion.objects.filter(created_at__gt=since)

    return JsonResponse({
        'cursor': timezone.now().isoformat(),
        'has_more': False,
        'full_refresh_required': False,
        'changes': {
            'representants': [_representant_json(r) for r in representants_qs],
            'avis': [_avis_json(a) for a in avis_qs],
            'reunions': [_reunion_json(r) for r in reunions_qs],
            'decisions': [_decision_json(d) for d in decisions_qs],
            'participants': [_participant_json(p) for p in participants_qs],
            'pieces_jointes': [_piece_jointe_json(p) for p in pieces_qs],
        },
    })


# --------------------------------------------------------------------------- #
#  mutations (push de l'outbox mobile)
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def mutations(request):
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'code': 'INVALID_JSON', 'message': 'Corps JSON invalide.'}, status=400)

    results = [_traiter_mutation(request, item) for item in body.get('mutations', [])]
    return JsonResponse({'results': results})


def _traiter_mutation(request, item):
    local_uuid = item.get('local_uuid')
    op = item.get('type')
    payload = item.get('payload') or {}
    base_out = {'local_uuid': local_uuid}
    try:
        if op == 'reunion.create':
            server_id = _mut_reunion_create(request, payload)
        elif op == 'reunion.update':
            server_id = _mut_reunion_update(payload)
        elif op == 'avis.upsert':
            server_id = _mut_avis_upsert(request, payload)
        elif op == 'decision.create':
            server_id = _mut_decision_create(payload)
        elif op == 'decision.update_statut':
            server_id = _mut_decision_update_statut(payload)
        elif op == 'participant.create':
            server_id = _mut_participant_create(payload)
        else:
            return {**base_out, 'status': 'rejected', 'errors': f"Type de mutation non supporté (V1) : {op}"}
    except _RejetValidation as exc:
        return {**base_out, 'status': 'rejected', 'errors': str(exc)}
    return {**base_out, 'status': 'accepted', 'server_id': server_id}


def _mut_reunion_create(request, payload):
    commune_id = (payload.get('commune_id') or '').strip()
    district_id = (payload.get('district_id') or '').strip()
    region_id = (payload.get('region_id') or '').strip()
    objet = (payload.get('objet') or '').strip()
    date_reunion = (payload.get('date_reunion') or '').strip()
    if not (commune_id or district_id or region_id) or not objet or not date_reunion:
        raise _RejetValidation('Commune (ou District ou Region), objet et date sont obligatoires.')

    type_reunion = (payload.get('type_reunion') or '').strip()
    if type_reunion and type_reunion not in dict(Reunion.TYPE_CHOICES):
        raise _RejetValidation('Type de reunion invalide.')

    client_id = (payload.get('id') or '').strip()
    if client_id:
        existante = Reunion.objects.filter(id=client_id).first()
        if existante:
            return str(existante.id)

    reunion = Reunion.objects.create(
        id=client_id or uuid.uuid4(),
        type_reunion=type_reunion or None,
        commune_id=commune_id or None,
        district_id=district_id or None,
        region_id=region_id or None,
        date_reunion=date_reunion,
        lieu=(payload.get('lieu') or '').strip() or None,
        objet=objet,
        compte_rendu=(payload.get('compte_rendu') or '').strip() or None,
        recommandations=(payload.get('recommandations') or '').strip() or None,
        organise_par_id=(payload.get('organise_par_id') or '').strip() or None,
        created_by=_current_employe(request),
    )
    return str(reunion.id)


def _mut_reunion_update(payload):
    reunion_id = (payload.get('id') or '').strip()
    if not reunion_id:
        raise _RejetValidation("L'id de la reunion est obligatoire pour une mise a jour.")
    try:
        reunion = Reunion.objects.get(id=reunion_id)
    except Reunion.DoesNotExist:
        raise _RejetValidation('Reunion introuvable.')

    if 'commune_id' in payload:
        reunion.commune_id = (payload.get('commune_id') or '').strip() or None
    if 'district_id' in payload:
        reunion.district_id = (payload.get('district_id') or '').strip() or None
    if 'region_id' in payload:
        reunion.region_id = (payload.get('region_id') or '').strip() or None
    if not (reunion.commune_id or reunion.district_id or reunion.region_id):
        raise _RejetValidation('La reunion doit avoir au moins une Commune, un District ou une Region.')
    if payload.get('date_reunion'):
        reunion.date_reunion = payload['date_reunion']
    if 'lieu' in payload:
        reunion.lieu = (payload.get('lieu') or '').strip() or None
    if payload.get('objet'):
        reunion.objet = payload['objet'].strip()
    if 'compte_rendu' in payload:
        reunion.compte_rendu = (payload.get('compte_rendu') or '').strip() or None
    if 'recommandations' in payload:
        reunion.recommandations = (payload.get('recommandations') or '').strip() or None
    if 'type_reunion' in payload:
        type_reunion = (payload.get('type_reunion') or '').strip()
        if type_reunion and type_reunion not in dict(Reunion.TYPE_CHOICES):
            raise _RejetValidation('Type de reunion invalide.')
        reunion.type_reunion = type_reunion or None
    reunion.save()
    return str(reunion.id)


def _mut_avis_upsert(request, payload):
    representant_id = (payload.get('representant_id') or '').strip()
    date_avis_raw = (payload.get('date_avis') or '').strip()
    if not representant_id or not date_avis_raw:
        raise _RejetValidation('Representant et date sont obligatoires.')
    try:
        date_avis = datetime.strptime(date_avis_raw, '%Y-%m-%d').date()
    except ValueError:
        raise _RejetValidation('Format de date invalide (attendu YYYY-MM-DD).')

    representant = _filter_representants_queryset_for_user(
        RepresentantUsager.objects.all(), request.user,
    ).filter(id=representant_id).first()
    if not representant:
        raise _RejetValidation('Representant introuvable ou hors de votre perimetre.')

    defaults = {
        'employe_id': (payload.get('employe_id') or '').strip() or None,
        'reunion_id': (payload.get('reunion_id') or '').strip() or None,
        'quantite_ok': bool(payload.get('quantite_ok')),
        'qualite_ok': bool(payload.get('qualite_ok')),
        'delai_reparation_ok': bool(payload.get('delai_reparation_ok')),
        'relation_gestionnaire_ok': bool(payload.get('relation_gestionnaire_ok')),
        'probleme_technique': (payload.get('probleme_technique') or '').strip() or None,
        'probleme_recouvrement': (payload.get('probleme_recouvrement') or '').strip() or None,
        'probleme_regles_utilisation': (payload.get('probleme_regles_utilisation') or '').strip() or None,
        'remarque': (payload.get('remarque') or '').strip() or None,
    }
    avis, _created = AvisRepresentant.objects.update_or_create(
        representant=representant, date_avis=date_avis, defaults=defaults,
    )
    return str(avis.id)


def _mut_decision_create(payload):
    reunion_id = (payload.get('reunion_id') or '').strip()
    description = (payload.get('description') or '').strip()
    if not reunion_id or not description:
        raise _RejetValidation('Reunion et description sont obligatoires.')
    if not Reunion.objects.filter(id=reunion_id).exists():
        raise _RejetValidation('Reunion introuvable.')

    client_id = (payload.get('id') or '').strip()
    if client_id and DecisionReunion.objects.filter(id=client_id).exists():
        return client_id

    decision = DecisionReunion.objects.create(
        id=client_id or uuid.uuid4(),
        reunion_id=reunion_id,
        description=description,
        responsable_id=(payload.get('responsable_id') or '').strip() or None,
        date_echeance=payload.get('date_echeance') or None,
        statut=payload.get('statut') or DecisionReunion.STATUT_A_FAIRE,
    )
    return str(decision.id)


def _mut_decision_update_statut(payload):
    decision_id = (payload.get('id') or '').strip()
    statut = (payload.get('statut') or '').strip()
    if not decision_id or statut not in dict(DecisionReunion.STATUT_CHOICES):
        raise _RejetValidation('Decision et statut valide sont obligatoires.')
    try:
        decision = DecisionReunion.objects.get(id=decision_id)
    except DecisionReunion.DoesNotExist:
        raise _RejetValidation('Decision introuvable.')
    decision.statut = statut
    if 'commentaire_suivi' in payload:
        decision.commentaire_suivi = (payload.get('commentaire_suivi') or '').strip() or None
    if statut == DecisionReunion.STATUT_REALISEE and not decision.date_realisation:
        decision.date_realisation = timezone.localdate()
    decision.save()
    return str(decision.id)


def _mut_participant_create(payload):
    reunion_id = (payload.get('reunion_id') or '').strip()
    type_participant = (payload.get('type_participant') or '').strip()
    if not reunion_id or type_participant not in dict(ParticipantReunion.TYPE_CHOICES):
        raise _RejetValidation('Reunion et type de participant valide sont obligatoires.')
    if not Reunion.objects.filter(id=reunion_id).exists():
        raise _RejetValidation('Reunion introuvable.')

    client_id = (payload.get('id') or '').strip()
    if client_id and ParticipantReunion.objects.filter(id=client_id).exists():
        return client_id

    participant = ParticipantReunion(
        id=client_id or uuid.uuid4(),
        reunion_id=reunion_id,
        type_participant=type_participant,
        present=payload.get('present', True),
        fonction_libre=(payload.get('fonction_libre') or '').strip() or None,
        contact_libre=(payload.get('contact_libre') or '').strip() or None,
    )
    ref_field = {
        ParticipantReunion.TYPE_REPRESENTANT: 'representant_id',
        ParticipantReunion.TYPE_ABONNE: 'point_eau_id',
        ParticipantReunion.TYPE_EMPLOYE: 'employe_id',
        ParticipantReunion.TYPE_AUTORITE: 'autorite_id',
        ParticipantReunion.TYPE_TIERS: 'tiers_id',
    }.get(type_participant)
    if ref_field:
        ref_id = (payload.get(ref_field) or '').strip()
        if not ref_id:
            raise _RejetValidation(f"Selectionnez une fiche existante pour le type '{type_participant}'.")
        setattr(participant, ref_field, ref_id)
    participant.save()
    return str(participant.id)


# --------------------------------------------------------------------------- #
#  pièces jointes (upload multipart, hors mutations JSON)
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def piece_jointe_upload(request, reunion_id):
    try:
        reunion = Reunion.objects.get(id=reunion_id)
    except Reunion.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Reunion introuvable.'}, status=404)

    fichier = request.FILES.get('fichier')
    if not fichier:
        return JsonResponse({'success': False, 'error': 'Aucun fichier fourni.'}, status=400)

    type_piece = request.POST.get('type_piece') or PieceJointeReunion.TYPE_AUTRE
    if type_piece not in dict(PieceJointeReunion.TYPE_CHOICES):
        type_piece = PieceJointeReunion.TYPE_AUTRE

    piece = PieceJointeReunion.objects.create(
        reunion=reunion,
        type_piece=type_piece,
        fichier=fichier,
        legende=(request.POST.get('legende') or '').strip() or None,
        uploaded_by=_current_employe(request),
    )
    return JsonResponse({'success': True, 'piece_jointe': _piece_jointe_json(piece)})


# --------------------------------------------------------------------------- #
#  notes avancées (adaptateur mobile au-dessus de notes/, entity_type/entity_id)
# --------------------------------------------------------------------------- #

@require_GET
@mobile_required
@_json_errors
def notes_for_entity(request, entity_type, entity_id):
    if not _notes_available():
        return JsonResponse({'success': False, 'error': 'NOTES_DISABLED', 'results': []})

    notes_qs = _accessible_notes_queryset(request.user).filter(
        is_archived=False, links__entity_type=entity_type, links__entity_id=entity_id,
    ).distinct().order_by('-updated_at')
    results = [
        {
            'id': str(note.id),
            'title': note.title,
            'content_text': note.content_text,
            'note_type': note.note_type,
            'updated_at': note.updated_at.isoformat(),
            'tags': list(note.tags.values_list('name', flat=True)),
            'tasks': [
                {'id': str(t.id), 'title': t.title, 'status': t.status, 'due_date': _iso(t.due_date)}
                for t in note.tasks.all()
            ],
        }
        for note in notes_qs[:50]
    ]
    return JsonResponse({'success': True, 'results': results})


@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def notes_quick_create(request):
    if not _notes_available():
        return JsonResponse({'success': False, 'error': 'NOTES_DISABLED'})

    entity_type = (request.POST.get('entity_type') or '').strip().lower()
    entity_id = (request.POST.get('entity_id') or '').strip()
    title = (request.POST.get('title') or '').strip()
    content = (request.POST.get('content') or '').strip()
    tags = (request.POST.get('tags') or '').strip()
    if not entity_type or not entity_id or not title:
        return JsonResponse({'success': False, 'error': 'Entite et titre requis.'}, status=400)

    note = Note.objects.create(
        title=title, note_type='note', status='active', visibility='private',
        content_json=[{'id': 'block-1', 'type': 'paragraph', 'text': content, 'meta': {}}],
        content_text=content, created_by=request.user, updated_by=request.user,
    )
    _replace_tags(note, tags)
    NoteLink.objects.create(
        note=note, entity_type=entity_type, entity_id=entity_id, label=request.POST.get('label', ''),
    )
    return JsonResponse({'success': True, 'note_id': str(note.id)})


@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def notes_add_task(request, note_id):
    if not _notes_available():
        return JsonResponse({'success': False, 'error': 'NOTES_DISABLED'})

    try:
        note = _accessible_notes_queryset(request.user).get(id=note_id)
    except Note.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Note introuvable.'}, status=404)

    title = (request.POST.get('title') or '').strip()
    if not title:
        return JsonResponse({'success': False, 'error': 'Titre de tache requis.'}, status=400)

    task = NoteTask.objects.create(
        note=note, title=title[:255], description=(request.POST.get('description') or '').strip(),
        due_date=request.POST.get('due_date') or None, status=request.POST.get('status') or 'todo',
    )
    return JsonResponse({'success': True, 'task_id': str(task.id)})
