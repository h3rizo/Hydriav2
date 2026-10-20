import re
import unicodedata
from uuid import UUID

from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q

from apps.employees.models import Employe
from apps.organization.models import Base
from apps.planning.models import Planning

from .models import Conversation, Message, Participant


REPAIR_KEY_PREFIX = "repair_planning:"


def _clean_text(value):
    raw = (value or "").strip().lower()
    normalized = unicodedata.normalize("NFD", raw)
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", "", without_accents).strip()


def _is_terminated_command(message_text):
    text = _clean_text(message_text)
    return text in {"termine", "terminee"} or text.startswith("termine ") or text.startswith("terminee ")


def _repair_key(planning_id):
    return f"{REPAIR_KEY_PREFIX}{planning_id}"


def _conversation_for_planning(planning):
    return Conversation.objects.filter(
        type="group",
        description__startswith=_repair_key(planning.id),
    ).first()


def _safe_actor(actor):
    return actor if isinstance(actor, Employe) else None


def _first_active_employee(queryset):
    return queryset.filter(date_debauchage__isnull=True).first()


def _target_organisation(planning):
    if planning.employe and planning.employe.base and planning.employe.base.organisation:
        return planning.employe.base.organisation

    if planning.ouvrage:
        base = Base.objects.filter(ouvrage=planning.ouvrage).select_related("organisation").first()
        if base and base.organisation:
            return base.organisation
    return None


def _target_base(planning):
    if planning.employe and planning.employe.base:
        return planning.employe.base

    if planning.ouvrage:
        return Base.objects.filter(ouvrage=planning.ouvrage).first()
    return None


def _build_participants(planning, actor=None):
    selected = {}

    def add(emp):
        if not emp:
            return
        if getattr(emp, "date_debauchage", None):
            return
        selected[str(emp.id)] = emp

    actor = _safe_actor(actor)
    add(actor)
    add(planning.employe)

    target_base = _target_base(planning)
    target_org = _target_organisation(planning)

    if target_base:
        responsable_ops = _first_active_employee(
            Employe.objects.filter(
                base=target_base,
                poste__isnull=False,
            ).filter(
                (
                    Q(poste__nom_poste__icontains="responsable")
                    | Q(poste__nom_poste__icontains="chef")
                )
                & (
                    Q(poste__nom_poste__icontains="operation")
                    | Q(poste__nom_poste__icontains="operat")
                    | Q(poste__nom_poste__icontains="technique")
                )
            )
        )
        if not responsable_ops:
            responsable_ops = _first_active_employee(
                Employe.objects.filter(
                    base=target_base,
                    poste__isnull=False,
                ).filter(
                    Q(poste__nom_poste__icontains="responsable")
                    | Q(poste__nom_poste__icontains="chef")
                )
            )
        add(responsable_ops)

    if target_org:
        directeur_adjoint = _first_active_employee(
            Employe.objects.filter(
                base__organisation=target_org,
                poste__isnull=False,
            ).filter(
                (Q(poste__nom_poste__icontains="directeur") & Q(poste__nom_poste__icontains="adjoint"))
                | Q(poste__nom_poste__icontains="dga")
            )
        )
        add(directeur_adjoint)

        directeur_org = _first_active_employee(
            Employe.objects.filter(
                base__organisation=target_org,
                poste__isnull=False,
                poste__nom_poste__icontains="directeur",
            ).exclude(poste__nom_poste__icontains="adjoint")
        )
        add(directeur_org)

    return list(selected.values())


def _ensure_participants(conversation, participants, admin=None):
    admin = _safe_actor(admin)
    for emp in participants:
        obj, _ = Participant.objects.get_or_create(
            conversation=conversation,
            employe=emp,
            defaults={"est_admin": bool(admin and emp.id == admin.id)},
        )
        if admin and emp.id == admin.id and not obj.est_admin:
            obj.est_admin = True
            obj.save(update_fields=["est_admin"])


def _post_system_once(conversation, content):
    if not content:
        return False
    content = content.strip()
    if conversation.messages.filter(type="system", contenu=content).exists():
        return False
    Message.objects.create(
        conversation=conversation,
        type="system",
        contenu=content,
        expediteur=None,
    )
    return True


def _participant_emails(participants):
    emails = []
    seen = set()
    for emp in participants:
        mail = (getattr(emp, "mail", "") or "").strip()
        if not mail:
            continue
        key = mail.lower()
        if key in seen:
            continue
        seen.add(key)
        emails.append(mail)
    return emails


def _send_repair_email(participants, planning):
    recipients = _participant_emails(participants)
    if not recipients:
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)
    if not from_email:
        return
    ouvrage_name = planning.ouvrage.nom_ouvrage if planning.ouvrage else "Sans ouvrage"
    activity = (planning.fiche_poste.tache or "").strip() if getattr(planning, "fiche_poste", None) else "Non precisee"
    remarque = (planning.remarque or "").strip() or "Aucune remarque"
    date_label = planning.date.strftime("%d/%m/%Y") if planning.date else "Sans date"
    assigne = planning.employe.nom_affichage if planning.employe else "Non assigne"

    subject = f"[Hydria] Reparation a suivre - {ouvrage_name}"
    body = (
        "Une reparation non terminee est a suivre dans Hydria.\n\n"
        f"Ouvrage: {ouvrage_name}\n"
        f"Date: {date_label}\n"
        f"Activite: {activity}\n"
        f"Remarque: {remarque}\n"
        f"Assigne a: {assigne}\n\n"
        "Consultez le module Conversations pour echanger avec l'equipe."
    )
    try:
        send_mail(subject, body, from_email, recipients, fail_silently=True)
    except Exception:
        pass


def _send_repair_completion_email(participants, planning):
    recipients = _participant_emails(participants)
    if not recipients:
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)
    if not from_email:
        return
    ouvrage_name = planning.ouvrage.nom_ouvrage if planning.ouvrage else "Sans ouvrage"
    activity = (planning.fiche_poste.tache or "").strip() if getattr(planning, "fiche_poste", None) else "Non precisee"
    date_label = planning.date.strftime("%d/%m/%Y") if planning.date else "Sans date"
    assigne = planning.employe.nom_affichage if planning.employe else "Non assigne"

    subject = f"[Hydria] Reparation terminee - {ouvrage_name}"
    body = (
        "Une reparation suivie dans Hydria vient d'etre marquee terminee.\n\n"
        f"Ouvrage: {ouvrage_name}\n"
        f"Date: {date_label}\n"
        f"Activite: {activity}\n"
        f"Assigne a: {assigne}\n\n"
        "Consultez le module Conversations pour l'historique complet."
    )
    try:
        send_mail(subject, body, from_email, recipients, fail_silently=True)
    except Exception:
        pass


def _repair_context_message(planning):
    ouvrage_name = planning.ouvrage.nom_ouvrage if planning.ouvrage else "ouvrage non defini"
    assigned_name = planning.employe.nom_affichage if planning.employe else "Non assigne"
    activite = (
        (planning.fiche_poste.tache or "").strip()
        if getattr(planning, "fiche_poste", None)
        else ""
    ) or "Non precisee"
    remarque = (planning.remarque or "").strip() or "Aucune remarque"
    date_label = planning.date.strftime("%d/%m/%Y") if planning.date else "Sans date"
    return (
        f"Suivi reparation actif - Ouvrage: {ouvrage_name} ({date_label})\n"
        f"Activite: {activite}\n"
        f"Remarque: {remarque}\n"
        f"Assigne a: {assigned_name}\n"
        "Repondez 'Termine' dans ce chat pour cloturer la reparation."
    )


def ensure_repair_conversation(planning, actor=None, notify=False):
    """
    Ensure an open conversation exists for a non-validated repair planning.
    Returns the conversation or None.
    """
    if planning.estvalide:
        return None

    actor = _safe_actor(actor)
    participants = _build_participants(planning, actor=actor)
    if not participants:
        return None

    conversation = _conversation_for_planning(planning)
    created = False
    if not conversation:
        creator = actor or planning.employe or participants[0]
        if not creator:
            return None

        ouvrage_name = planning.ouvrage.nom_ouvrage if planning.ouvrage else "Sans ouvrage"
        date_label = planning.date.strftime("%d/%m/%Y") if planning.date else "Sans date"
        conversation = Conversation.objects.create(
            type="group",
            nom_groupe=f"Reparation - {ouvrage_name} - {date_label}",
            description=f"{_repair_key(planning.id)}\nSuivi automatique des reparations.",
            createur=creator,
            archivee=False,
        )
        created = True

    _ensure_participants(conversation, participants, admin=actor)

    if conversation.archivee:
        conversation.archivee = False
        conversation.save(update_fields=["archivee"])

    created_notice = _post_system_once(conversation, _repair_context_message(planning))
    if created_notice:
        _send_repair_email(participants, planning)

    return conversation


def close_repair_conversation(planning, actor=None, reason="", notify_completion=True):
    """
    Archive linked conversation when repair is done/validated/cancelled.

    notify_completion=False pour les fermetures qui ne sont pas une vraie
    reparation terminee (suppression, transfert de pieces...) : evite d'envoyer
    un email "reparation terminee" incorrect dans ces cas.

    L'envoi est garde par l'etat (was_archived), pas par le texte du message
    système : un texte different a chaque appel contournerait un dedup par
    contenu, alors qu'on ne veut jamais notifier deux fois la meme cloture.
    """
    conversation = _conversation_for_planning(planning)
    if not conversation:
        return None

    was_archived = conversation.archivee
    message = reason.strip() if reason else "Reparation terminee. Discussion archivee automatiquement."
    _post_system_once(conversation, message)

    if notify_completion and not was_archived:
        participants = [p.employe for p in conversation.participants.select_related("employe").all()]
        _send_repair_completion_email(participants, planning)

    if not conversation.archivee:
        conversation.archivee = True
        conversation.save(update_fields=["archivee"])

    return conversation


def extract_repair_planning_id(conversation):
    if not conversation or not conversation.description:
        return None

    match = re.search(rf"{REPAIR_KEY_PREFIX}([0-9a-fA-F-]{{36}})", conversation.description)
    if not match:
        return None

    try:
        return UUID(match.group(1))
    except ValueError:
        return None


def try_complete_repair_from_message(conversation, sender, text):
    """
    If the message is 'Termine' on a repair-linked conversation, close planning + chat.
    Returns dict with action state.
    """
    planning_id = extract_repair_planning_id(conversation)
    if not planning_id:
        return {"matched": False, "completed": False}

    if not _is_terminated_command(text):
        return {"matched": True, "completed": False}

    planning = Planning.objects.filter(id=planning_id).first()
    if not planning:
        return {"matched": True, "completed": False}

    if not planning.estvalide:
        planning.estvalide = True
        planning.save(update_fields=["estvalide"])

    sender_name = sender.nom_affichage if sender else "Utilisateur"
    close_repair_conversation(
        planning,
        actor=sender,
        reason=f"Reparation marquee terminee via messagerie par {sender_name}.",
    )
    return {"matched": True, "completed": True, "planning_id": str(planning.id)}
