import json
import logging

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (
    ReseauAvailabilitySlot,
    ReseauMagicLink,
    ReseauMeeting,
    ReseauMeetingConfirmation,
    ReseauMeetingSession,
    ReseauParticipant,
    ReseauParticipantAvailability,
    ReseauParticipantUnavailability,
)
from .services_reseau import (
    send_confirmation_email,
    send_magic_link_email,
    send_slot_match_alert_email,
)


SESSION_KEY = 'reseau_participant_id'
SESSION_SESSION_KEY = 'reseau_session_id'
logger = logging.getLogger(__name__)


def _build_session_countdown(session_obj):
    today = timezone.localdate()
    target_year = None
    if session_obj.date_debut:
        target_year = session_obj.date_debut.year
    elif session_obj.date_fin:
        target_year = session_obj.date_fin.year
    else:
        target_year = today.year

    target_date = today.replace(year=target_year, month=5, day=20)
    # Inclusive countdown: 18 avril -> 20 mai is displayed as 33 jours.
    days_remaining = max((target_date - today).days + 1, 0)
    weeks_remaining = round(days_remaining / 7, 1) if days_remaining else 0
    return {
        'days_remaining': days_remaining,
        'weeks_remaining': weeks_remaining,
        'is_finished': target_date < today,
        'target_date': target_date,
    }


@require_GET
def reseau_entry_index(request):
    session_obj = (
        ReseauMeetingSession.objects.filter(
            statut__in=[
                ReseauMeetingSession.STATUS_OPEN,
                ReseauMeetingSession.STATUS_DRAFT,
            ]
        )
        .order_by('date_debut', 'created_at')
        .first()
    )
    if not session_obj:
        messages.error(request, "Aucune session reseau n'est disponible pour le moment.")
        return redirect('login')
    return redirect('usagers:reseau_entry', session_slug=session_obj.slug)


def _serialize_slot(slot, selected_ids):
    participants_qs = slot.participant_availabilities.all()
    
    # Sort participants so current participant's selections might be at the top, or just alphabetically
    participants_dispos = [
        {'id': str(pa.participant.id), 'nom': pa.participant.nom}
        for pa in participants_qs
    ]
    
    available_count = len(participants_dispos)
    threshold = slot.session.seuil_confirmation
    local_start = timezone.localtime(slot.start_at)
    local_end = timezone.localtime(slot.end_at)
    
    meetings = [
        {
            'id': str(m.id),
            'status': m.status,
            'created_by_id': str(m.created_by_id) if m.created_by_id else '',
            'confirmed_participant_ids': [
                str(item.participant_id)
                for item in getattr(m, 'confirmations_qs', m.confirmations.all())
                if item.confirmed_at
            ],
            'participants': [{'id': str(p.id), 'nom': p.nom} for p in m.participants.all()]
        }
        for m in getattr(slot, 'meetings_qs', slot.meetings.all())
    ]

    return {
        'id': str(slot.id),
        'start_label': local_start.strftime('%d/%m/%Y %H:%M'),
        'end_label': local_end.strftime('%H:%M'),
        'start_iso': local_start.isoformat(),
        'end_iso': local_end.isoformat(),
        'date_label': local_start.strftime('%d/%m'),
        'day_label': local_start.strftime('%a').capitalize(),
        'time_label': local_start.strftime('%H:%M'),
        'available_count': available_count,
        'participants': participants_dispos,
        'meetings': meetings,
        'is_selected': str(slot.id) in selected_ids,
        'eligible': available_count >= threshold,
        'is_confirmed': slot.session.confirmed_slot_id == slot.id,
    }


def _build_portal_context(session_obj, participant):
    selected_ids = set(
        participant.availabilities.values_list('slot_id', flat=True)
    )
    from django.db.models import Prefetch
    slots = list(
        session_obj.slots.filter(is_active=True)
        .prefetch_related(
            'participant_availabilities__participant',
            'meetings__participants',
            'meetings__confirmations',
        )
        .order_by('start_at')
    )
    # attach the meetings_qs
    for slot in slots:
        slot.meetings_qs = slot.meetings.all()
        for meeting in slot.meetings_qs:
            meeting.confirmations_qs = meeting.confirmations.all()
    
    return {
        'session_obj': session_obj,
        'participant': participant,
        'slots': [_serialize_slot(slot, {str(item) for item in selected_ids}) for slot in slots],
        'unavailabilities': [
            {
                'id': str(item.id),
                'start_iso': timezone.localtime(item.start_at).strftime('%Y-%m-%dT%H:%M'),
                'end_iso': timezone.localtime(item.end_at).strftime('%Y-%m-%dT%H:%M'),
                'label': f"{timezone.localtime(item.start_at).strftime('%d/%m %H:%M')} - {timezone.localtime(item.end_at).strftime('%d/%m %H:%M')}",
            }
            for item in participant.unavailabilities.order_by('start_at')
        ],
        'confirmed_slot_id': str(session_obj.confirmed_slot_id) if session_obj.confirmed_slot_id else '',
        'threshold': session_obj.seuil_confirmation,
        'countdown': _build_session_countdown(session_obj),
    }


def _get_authenticated_participant(request, session_slug):
    participant_id = request.session.get(SESSION_KEY)
    session_id = request.session.get(SESSION_SESSION_KEY)
    if not participant_id or not session_id:
        return None
    try:
        return ReseauParticipant.objects.select_related('session').get(
            id=participant_id,
            session_id=session_id,
            session__slug=session_slug,
            actif=True,
        )
    except ReseauParticipant.DoesNotExist:
        return None


@require_GET
def reseau_entry(request, session_slug):
    session_obj = get_object_or_404(ReseauMeetingSession, slug=session_slug)
    participant = _get_authenticated_participant(request, session_slug)
    if participant:
        return redirect('usagers:reseau_portal', session_slug=session_slug)
    return render(request, 'usagers/reseau_entry.html', {'session_obj': session_obj})


@require_POST
def reseau_request_magic_link(request, session_slug):
    session_obj = get_object_or_404(ReseauMeetingSession, slug=session_slug)
    email = (request.POST.get('email') or '').strip().lower()
    nom = (request.POST.get('nom') or '').strip()
    
    participant = ReseauParticipant.objects.filter(
        session=session_obj,
        email__iexact=email,
        actif=True,
    ).first()
    
    # Auto-inscription si le participant n'existe pas encore
    if not participant and email:
        display_name = nom if nom else email.split('@')[0]
        participant = ReseauParticipant.objects.create(
            session=session_obj,
            email=email,
            nom=display_name,
            actif=True
        )
    elif participant and nom and participant.nom != nom:
        # Met à jour le nom si l'utilisateur en fournit un nouveau
        participant.nom = nom
        participant.save(update_fields=['nom'])

    if participant:
        participant.last_login_at = timezone.now()
        participant.save(update_fields=['last_login_at'])
        
        request.session[SESSION_KEY] = str(participant.id)
        request.session[SESSION_SESSION_KEY] = str(participant.session_id)
        
        # Enregistrer explicitement la session pour éviter les bugs
        request.session.modified = True

        messages.success(
            request,
            f"✅ Bienvenue {participant.nom} ! Vous êtes connecté au calendrier."
        )

    return redirect('usagers:reseau_portal', session_slug=session_slug)


@require_GET
def reseau_magic_login(request, token):
    # token is now the participant ID
    try:
        import uuid
        uid = uuid.UUID(token)
        participant = ReseauParticipant.objects.select_related('session').get(id=uid)
    except Exception as e:
        all_ids = list(ReseauParticipant.objects.values_list('id', flat=True))
        raise Http404(f"Participant {token} non trouvé. Erreur: {str(e)}. IDs existants: {[str(x) for x in all_ids]}")

    participant.last_login_at = timezone.now()
    participant.save(update_fields=['last_login_at'])

    request.session[SESSION_KEY] = str(participant.id)
    request.session[SESSION_SESSION_KEY] = str(participant.session_id)
    return redirect('usagers:reseau_portal', session_slug=participant.session.slug)


@require_GET
def reseau_magic_login(request, token):
    participant = None

    magic_link = (
        ReseauMagicLink.objects
        .select_related('participant', 'participant__session')
        .filter(token=token)
        .first()
    )
    if magic_link:
        if not magic_link.is_valid:
            raise Http404("Lien d'acces expire ou deja utilise.")
        magic_link.used_at = timezone.now()
        magic_link.save(update_fields=['used_at'])
        participant = magic_link.participant

    if participant is None:
        try:
            uuid_module = __import__('uuid')
            uid = uuid_module.UUID(str(token))
        except (TypeError, ValueError):
            uid = None

        if uid is not None:
            participant = (
                ReseauParticipant.objects
                .select_related('session')
                .filter(id=uid, actif=True)
                .first()
            )

    if participant is None:
        raise Http404("Lien d'acces invalide.")

    participant.last_login_at = timezone.now()
    participant.save(update_fields=['last_login_at'])

    request.session[SESSION_KEY] = str(participant.id)
    request.session[SESSION_SESSION_KEY] = str(participant.session_id)
    request.session.modified = True
    return redirect('usagers:reseau_portal', session_slug=participant.session.slug)


@require_GET
def reseau_portal(request, session_slug):
    participant = _get_authenticated_participant(request, session_slug)
    session_obj = get_object_or_404(ReseauMeetingSession, slug=session_slug)
    if not participant:
        return redirect('usagers:reseau_entry', session_slug=session_slug)

    return render(
        request,
        'usagers/reseau_portal.html',
        _build_portal_context(session_obj, participant),
    )


@require_GET
def reseau_meetings_overview(request, session_slug):
    participant = _get_authenticated_participant(request, session_slug)
    session_obj = get_object_or_404(ReseauMeetingSession, slug=session_slug)
    if not participant:
        return redirect('usagers:reseau_entry', session_slug=session_slug)

    now = timezone.now()
    meetings = list(
        session_obj.meetings.select_related('slot')
        .prefetch_related('participants')
        .order_by('slot__start_at', 'created_at')
    )
    participants_stats = list(
        session_obj.participants.filter(actif=True)
        .annotate(
            meetings_count=Count('meetings', distinct=True),
            proposed_count=Count('meetings', filter=Q(meetings__status='proposed'), distinct=True),
            planned_count=Count('meetings', filter=Q(meetings__status='planned'), distinct=True),
            completed_count=Count('meetings', filter=Q(meetings__status='completed'), distinct=True),
            overdue_planned_count=Count(
                'meetings',
                filter=Q(meetings__status='planned', meetings__slot__end_at__lt=now),
                distinct=True,
            ),
        )
        .order_by('-completed_count', '-planned_count', 'nom', 'email')
    )
    success_target = 3
    for item in participants_stats:
        item.remaining_to_target = max(success_target - item.completed_count, 0)
    participants_success_count = sum(1 for item in participants_stats if item.completed_count >= success_target)
    proposed_meetings_count = sum(1 for item in meetings if item.status == 'proposed')
    planned_meetings_count = sum(1 for item in meetings if item.status == 'planned' and item.slot.end_at >= now)
    completed_meetings_count = sum(1 for item in meetings if item.status == 'completed')
    overdue_planned_meetings_count = sum(1 for item in meetings if item.status == 'planned' and item.slot.end_at < now)

    return render(
        request,
        'usagers/reseau_meetings_overview.html',
        {
            'session_obj': session_obj,
            'participant': participant,
            'meetings': meetings,
            'participants_stats': participants_stats,
            'total_meetings': len(meetings),
            'participants_with_meetings': sum(1 for item in participants_stats if item.meetings_count),
            'success_target': success_target,
            'participants_success_count': participants_success_count,
            'proposed_meetings_count': proposed_meetings_count,
            'planned_meetings_count': planned_meetings_count,
            'completed_meetings_count': completed_meetings_count,
            'overdue_planned_meetings_count': overdue_planned_meetings_count,
            'now': now,
            'countdown': _build_session_countdown(session_obj),
            },
    )


@require_POST
def reseau_update_availability(request, session_slug):
    participant = _get_authenticated_participant(request, session_slug)
    if not participant:
        return JsonResponse({'success': False, 'error': 'Session expirée'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload invalide'}, status=400)

    import datetime
    
    selected_slot_ids = payload.get('slot_ids') or []
    existing_ids = []
    new_proposals = []
    
    for sid in selected_slot_ids:
        if isinstance(sid, str) and sid.startswith('new_'):
            try:
                _, date_str, time_str = sid.split('_')
                new_proposals.append((date_str, time_str))
            except ValueError:
                pass
        else:
            existing_ids.append(sid)

    participants_to_alert_by_slot = {}

    with transaction.atomic():
        for date_str, time_str in new_proposals:
            try:
                naive_start = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                aware_start = timezone.make_aware(naive_start, timezone.get_current_timezone())
                aware_end = aware_start + datetime.timedelta(hours=1)
                
                slot, created = ReseauAvailabilitySlot.objects.get_or_create(
                    session=participant.session,
                    start_at=aware_start,
                    end_at=aware_end,
                    defaults={'is_active': True}
                )
                existing_ids.append(str(slot.id))
            except Exception:
                pass

        valid_slots = list(
            ReseauAvailabilitySlot.objects.filter(
                session=participant.session,
                is_active=True,
                id__in=existing_ids,
            )
        )
        valid_slot_ids = {slot.id for slot in valid_slots}

        participant.availabilities.exclude(slot_id__in=valid_slot_ids).delete()
        existing_availabilities = set(
            participant.availabilities.filter(slot_id__in=valid_slot_ids).values_list('slot_id', flat=True)
        )
        newly_added_slots = [slot for slot in valid_slots if slot.id not in existing_availabilities]

        if newly_added_slots:
            for availability in (
                ReseauParticipantAvailability.objects
                .filter(slot__in=newly_added_slots)
                .exclude(participant=participant)
                .select_related('participant', 'slot')
            ):
                participants_to_alert_by_slot.setdefault(availability.slot_id, []).append(availability.participant)

        ReseauParticipantAvailability.objects.bulk_create(
            [
                ReseauParticipantAvailability(participant=participant, slot=slot)
                for slot in valid_slots
                if slot.id not in existing_availabilities
            ],
            ignore_conflicts=True,
        )

        for slot in newly_added_slots:
            recipients = participants_to_alert_by_slot.get(slot.id, [])
            if not recipients:
                continue

            def _send_alerts(slot_obj=slot, recipients_list=recipients):
                for recipient in recipients_list:
                    try:
                        send_slot_match_alert_email(participant.session, slot_obj, participant, recipient)
                    except Exception:
                        logger.exception(
                            "Erreur envoi alerte disponibilite partagee session=%s slot=%s recipient=%s actor=%s",
                            participant.session_id,
                            slot_obj.id,
                            recipient.id,
                            participant.id,
                        )

            transaction.on_commit(_send_alerts)

    context = _build_portal_context(participant.session, participant)
    return JsonResponse({'success': True, 'slots': context['slots']})


@require_POST
def reseau_add_unavailability(request, session_slug):
    participant = _get_authenticated_participant(request, session_slug)
    if not participant:
        return JsonResponse({'success': False, 'error': 'Session expirée'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload invalide'}, status=400)

    start_raw = payload.get('start_at')
    end_raw = payload.get('end_at')
    if not start_raw or not end_raw:
        return JsonResponse({'success': False, 'error': 'Dates requises'}, status=400)

    try:
        start_at = timezone.make_aware(timezone.datetime.fromisoformat(start_raw), timezone.get_current_timezone())
        end_at = timezone.make_aware(timezone.datetime.fromisoformat(end_raw), timezone.get_current_timezone())
    except Exception:
        return JsonResponse({'success': False, 'error': 'Format de date invalide'}, status=400)

    if end_at <= start_at:
        return JsonResponse({'success': False, 'error': 'La fin doit être après le début'}, status=400)

    with transaction.atomic():
        ReseauParticipantUnavailability.objects.create(
            participant=participant,
            start_at=start_at,
            end_at=end_at,
        )
        overlapping_slot_ids = list(
            ReseauAvailabilitySlot.objects.filter(
                session=participant.session,
                start_at__lt=end_at,
                end_at__gt=start_at,
            ).values_list('id', flat=True)
        )
        if overlapping_slot_ids:
            participant.availabilities.filter(slot_id__in=overlapping_slot_ids).delete()

    context = _build_portal_context(participant.session, participant)
    return JsonResponse({
        'success': True,
        'slots': context['slots'],
        'unavailabilities': context['unavailabilities'],
    })


@require_POST
def reseau_remove_unavailability(request, session_slug, unavailability_id):
    participant = _get_authenticated_participant(request, session_slug)
    if not participant:
        return JsonResponse({'success': False, 'error': 'Session expirée'}, status=403)

    deleted, _ = ReseauParticipantUnavailability.objects.filter(
        id=unavailability_id,
        participant=participant,
    ).delete()
    if not deleted:
        return JsonResponse({'success': False, 'error': 'Indisponibilité introuvable'}, status=404)

    context = _build_portal_context(participant.session, participant)
    return JsonResponse({
        'success': True,
        'slots': context['slots'],
        'unavailabilities': context['unavailabilities'],
    })


@require_POST
def reseau_create_meeting(request, session_slug):
    participant = _get_authenticated_participant(request, session_slug)
    if not participant:
        return JsonResponse({'success': False, 'error': 'Session expirée'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload invalide'}, status=400)

    slot_id = payload.get('slot_id')
    participant_ids = payload.get('participant_ids', [])

    slot = get_object_or_404(
        ReseauAvailabilitySlot,
        session=participant.session,
        id=slot_id,
        is_active=True
    )
    
    if not participant_ids:
        return JsonResponse({'success': False, 'error': 'Veuillez sélectionner au moins un participant (vous-même)'}, status=400)

    with transaction.atomic():
        selected_participants = list(
            participant.session.participants.filter(
                actif=True,
                id__in=participant_ids,
            ).distinct()
        )
        selected_participant_ids = {str(item.id) for item in selected_participants}
        if str(participant.id) not in selected_participant_ids:
            return JsonResponse({'success': False, 'error': "L'organisateur doit faire partie du rendez-vous."}, status=400)
        if len(selected_participants) < 2:
            return JsonResponse({'success': False, 'error': 'Veuillez selectionner au moins une autre personne.'}, status=400)

        meeting = ReseauMeeting.objects.create(
            session=participant.session,
            slot=slot,
            created_by=participant,
            status=ReseauMeeting.STATUS_PROPOSED,
        )
        meeting.participants.set(selected_participants)
        ReseauMeetingConfirmation.objects.bulk_create(
            [
                ReseauMeetingConfirmation(
                    meeting=meeting,
                    participant=item,
                    confirmed_at=timezone.now() if item.id == participant.id else None,
                )
                for item in selected_participants
            ],
            ignore_conflicts=True,
        )

    return JsonResponse({
        'success': True,
        'message': 'Proposition de rendez-vous envoyee. En attente des confirmations des autres participants.',
    })


@require_POST
def reseau_complete_meeting(request, session_slug, meeting_id):
    participant = _get_authenticated_participant(request, session_slug)
    if not participant:
        return redirect('usagers:reseau_entry', session_slug=session_slug)

    meeting = get_object_or_404(
        participant.session.meetings.select_related('slot'),
        id=meeting_id,
    )
    if meeting.status != 'completed':
        meeting.status = 'completed'
        meeting.completed_at = timezone.now()
        meeting.save(update_fields=['status', 'completed_at'])
    return redirect('usagers:reseau_meetings_overview', session_slug=session_slug)


@require_POST
def reseau_confirm_meeting(request, session_slug, meeting_id):
    participant = _get_authenticated_participant(request, session_slug)
    if not participant:
        return JsonResponse({'success': False, 'error': 'Session expiree'}, status=403)

    meeting = get_object_or_404(
        participant.session.meetings.prefetch_related('participants', 'confirmations'),
        id=meeting_id,
    )
    if not meeting.participants.filter(id=participant.id).exists():
        return JsonResponse({'success': False, 'error': 'Acces refuse'}, status=403)
    if meeting.status == ReseauMeeting.STATUS_COMPLETED:
        return JsonResponse({'success': False, 'error': 'Ce rendez-vous est deja termine.'}, status=400)

    with transaction.atomic():
        confirmation, _ = ReseauMeetingConfirmation.objects.get_or_create(
            meeting=meeting,
            participant=participant,
            defaults={'confirmed_at': timezone.now()},
        )
        if confirmation.confirmed_at is None:
            confirmation.confirmed_at = timezone.now()
            confirmation.save(update_fields=['confirmed_at'])

        total_participants = meeting.participants.count()
        confirmed_count = meeting.confirmations.filter(confirmed_at__isnull=False).count()
        if total_participants and confirmed_count >= total_participants and meeting.status != ReseauMeeting.STATUS_PLANNED:
            meeting.status = ReseauMeeting.STATUS_PLANNED
            meeting.save(update_fields=['status'])

    context = _build_portal_context(participant.session, participant)
    return JsonResponse({'success': True, 'slots': context['slots']})


@require_POST
def reseau_delete_meeting(request, session_slug, meeting_id):
    participant = _get_authenticated_participant(request, session_slug)
    is_json = request.content_type == 'application/json' or request.headers.get('Content-Type') == 'application/json'

    if not participant:
        if is_json:
            return JsonResponse({'success': False, 'error': 'Session expirée'}, status=403)
        return redirect('usagers:reseau_entry', session_slug=session_slug)

    meeting = get_object_or_404(
        participant.session.meetings.select_related('slot'),
        id=meeting_id,
    )
    meeting.delete()
    
    if is_json:
        return JsonResponse({'success': True})
    return redirect('usagers:reseau_meetings_overview', session_slug=session_slug)


@require_POST
def reseau_confirm_slot(request, session_slug, slot_id):
    participant = _get_authenticated_participant(request, session_slug)
    if not participant:
        return JsonResponse({'success': False, 'error': 'Session expirée'}, status=403)

    session_obj = participant.session
    slot = get_object_or_404(
        ReseauAvailabilitySlot.objects.annotate(available_count=Count('participant_availabilities')),
        session=session_obj,
        id=slot_id,
        is_active=True,
    )
    if slot.available_count < session_obj.seuil_confirmation:
        return JsonResponse({'success': False, 'error': 'Ce creneau ne remplit pas encore le seuil.'}, status=400)

    participants = list(
        session_obj.participants.filter(
            actif=True,
            availabilities__slot=slot,
        ).distinct()
    )

    try:
        google_link = send_confirmation_email(session_obj, slot, participants)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f'Envoi email impossible: {exc}'}, status=500)

    session_obj.confirmed_slot = slot
    session_obj.statut = ReseauMeetingSession.STATUS_CONFIRMED
    session_obj.confirmation_envoyee_at = timezone.now()
    session_obj.save(update_fields=['confirmed_slot', 'statut', 'confirmation_envoyee_at', 'updated_at'])

    context = _build_portal_context(session_obj, participant)
    return JsonResponse({'success': True, 'slots': context['slots'], 'google_link': google_link})


@require_POST
def reseau_logout(request, session_slug):
    request.session.pop(SESSION_KEY, None)
    request.session.pop(SESSION_SESSION_KEY, None)
    return redirect('usagers:reseau_entry', session_slug=session_slug)
