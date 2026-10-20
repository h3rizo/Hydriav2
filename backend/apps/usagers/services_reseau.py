from datetime import timedelta
from urllib.parse import urlencode
import secrets

from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import ReseauMagicLink


def get_public_base_url():
    return getattr(settings, 'SITE_BASE_URL', 'https://www.hydria.mg').rstrip('/')


def build_absolute_url(path):
    return f"{get_public_base_url()}{path}"


def create_magic_link(participant, lifetime_hours=24):
    token = secrets.token_urlsafe(32)
    return ReseauMagicLink.objects.create(
        participant=participant,
        token=token,
        expires_at=timezone.now() + timedelta(hours=lifetime_hours),
    )


def send_magic_link_email(participant):
    magic_link = create_magic_link(participant)
    access_path = reverse('usagers:reseau_magic_login', kwargs={'token': magic_link.token})
    access_url = build_absolute_url(access_path)
    session_url = build_absolute_url(
        reverse('usagers:reseau_portal', kwargs={'session_slug': participant.session.slug})
    )

    subject = f"Acces calendrier reseau - {participant.session.titre}"
    body = render_to_string('usagers/reseau_magic_email.txt', {
        'participant': participant,
        'session_obj': participant.session,
        'access_url': access_url,
        'session_url': session_url,
        'expires_at': magic_link.expires_at,
    })
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
    send_mail(subject, body, from_email, [participant.email], fail_silently=False)
    return magic_link


def build_google_calendar_link(session_obj, slot, attendee_emails):
    params = {
        'action': 'TEMPLATE',
        'text': session_obj.titre,
        'dates': f"{slot.start_at:%Y%m%dT%H%M%SZ}/{slot.end_at:%Y%m%dT%H%M%SZ}",
        'details': session_obj.description or '',
        'location': session_obj.lieu or '',
    }
    if attendee_emails:
        params['add'] = ','.join(sorted(set(attendee_emails)))
    return f"https://calendar.google.com/calendar/render?{urlencode(params)}"


def build_ics_content(session_obj, slot, attendee_emails):
    description = (session_obj.description or '').replace('\n', '\\n')
    location = session_obj.lieu or ''
    attendees = ''.join(
        f"ATTENDEE;CN={email}:MAILTO:{email}\r\n"
        for email in sorted(set(attendee_emails))
    )
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Hydria//Reseau Meetings//FR\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{session_obj.id}-{slot.id}@hydria.mg\r\n"
        f"DTSTAMP:{timezone.now():%Y%m%dT%H%M%SZ}\r\n"
        f"DTSTART:{slot.start_at:%Y%m%dT%H%M%SZ}\r\n"
        f"DTEND:{slot.end_at:%Y%m%dT%H%M%SZ}\r\n"
        f"SUMMARY:{session_obj.titre}\r\n"
        f"DESCRIPTION:{description}\r\n"
        f"LOCATION:{location}\r\n"
        f"{attendees}"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def send_confirmation_email(session_obj, slot, participants):
    attendee_emails = [p.calendar_email for p in participants if p.calendar_email]
    google_link = build_google_calendar_link(session_obj, slot, attendee_emails)
    body = render_to_string('usagers/reseau_confirmation_email.txt', {
        'session_obj': session_obj,
        'slot': slot,
        'participants': participants,
        'google_link': google_link,
    })
    email = EmailMessage(
        subject=f"Rendez-vous confirme - {session_obj.titre}",
        body=body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None),
        to=attendee_emails,
    )
    email.attach(
        filename='rendez-vous.ics',
        content=build_ics_content(session_obj, slot, attendee_emails),
        mimetype='text/calendar',
    )
    email.send(fail_silently=False)
    return google_link


def send_slot_match_alert_email(session_obj, slot, actor, recipient):
    if not recipient.email:
        return

    magic_link = create_magic_link(recipient)
    access_path = reverse('usagers:reseau_magic_login', kwargs={'token': magic_link.token})
    access_url = build_absolute_url(access_path)
    session_url = build_absolute_url(
        reverse('usagers:reseau_portal', kwargs={'session_slug': session_obj.slug})
    )
    body = render_to_string('usagers/reseau_match_alert_email.txt', {
        'session_obj': session_obj,
        'slot': slot,
        'actor': actor,
        'recipient': recipient,
        'access_url': access_url,
        'session_url': session_url,
        'expires_at': magic_link.expires_at,
    })
    send_mail(
        subject=f"Alerte disponibilite partagee - {session_obj.titre}",
        message=body,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None),
        recipient_list=[recipient.email],
        fail_silently=False,
    )
