from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.usagers.models import (
    ReseauAvailabilitySlot,
    ReseauMeetingSession,
    ReseauParticipant,
    ReseauParticipantAvailability,
)


class Command(BaseCommand):
    help = "Cree un jeu de donnees de demonstration pour le workflow reseau."

    def handle(self, *args, **options):
        session_obj, created = ReseauMeetingSession.objects.get_or_create(
            slug='demo-reseau',
            defaults={
                'titre': 'Reunion reseau de demonstration',
                'description': "Session de test pour valider le parcours de disponibilites.",
                'lieu': 'Visioconference Google Meet',
                'duree_minutes': 60,
                'seuil_confirmation': 2,
                'statut': ReseauMeetingSession.STATUS_OPEN,
                'date_debut': timezone.localdate(),
                'date_fin': timezone.localdate() + timedelta(days=7),
            },
        )

        if not created:
            session_obj.statut = ReseauMeetingSession.STATUS_OPEN
            session_obj.seuil_confirmation = 2
            session_obj.save(update_fields=['statut', 'seuil_confirmation', 'updated_at'])

        participants = []
        demo_participants = [
            ('Alice Reseau', 'alice.reseau@example.com'),
            ('Bruno Reseau', 'bruno.reseau@example.com'),
            ('Clara Reseau', 'clara.reseau@example.com'),
        ]
        for nom, email in demo_participants:
            participant, _ = ReseauParticipant.objects.get_or_create(
                session=session_obj,
                email=email,
                defaults={
                    'nom': nom,
                    'google_calendar_email': email,
                    'actif': True,
                },
            )
            participants.append(participant)

        local_tz = timezone.get_current_timezone()
        base_date = timezone.localdate() + timedelta(days=1)
        base_slots = [
            (9, 0),
            (11, 0),
            (14, 0),
        ]

        slots = []
        for hour, minute in base_slots:
            naive_start = datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute)
            start_at = timezone.make_aware(naive_start, local_tz)
            end_at = start_at + timedelta(minutes=session_obj.duree_minutes)
            slot, _ = ReseauAvailabilitySlot.objects.get_or_create(
                session=session_obj,
                start_at=start_at,
                end_at=end_at,
                defaults={'is_active': True},
            )
            slots.append(slot)

        demo_availability = {
            participants[0].email: [0, 1],
            participants[1].email: [0, 2],
            participants[2].email: [1, 2],
        }
        for participant in participants:
            for slot_index in demo_availability.get(participant.email, []):
                ReseauParticipantAvailability.objects.get_or_create(
                    participant=participant,
                    slot=slots[slot_index],
                )

        self.stdout.write(self.style.SUCCESS(
            f"Session reseau demo prete: /usagers/reseau/{session_obj.slug}/"
        ))
