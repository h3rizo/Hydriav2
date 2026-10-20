import datetime
import decimal
import json
import uuid

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.system.models import ActivityLog
from apps.system.request_context import get_current_user


ALERT_GROUP_KEY = "system_audit_alerts_v1"
MAX_CHANGED_FIELDS = 40
MAX_CREATE_DELETE_FIELDS = 60
MAX_FIELD_VALUE_LENGTH = 400

EXCLUDED_APPS = {
    "admin",
    "contenttypes",
    "migrations",
    "sessions",
}

EXCLUDED_MODELS = {
    ("system", "activitylog"),
    ("system", "pagevisit"),
    ("system", "userpresence"),
    ("system", "passwordresetcode"),
    ("employees", "positiongpsemploye"),
    ("messaging", "conversation"),
    ("messaging", "participant"),
    ("messaging", "message"),
    ("messaging", "call"),
}


def _is_trackable(instance):
    if instance is None:
        return False

    if instance.__class__.__module__ == "__fake__":
        return False

    opts = instance._meta
    if opts.auto_created or opts.proxy:
        return False

    if opts.db_table == "django_migrations":
        return False

    if opts.app_label in EXCLUDED_APPS:
        return False

    if (opts.app_label, opts.model_name) in EXCLUDED_MODELS:
        return False

    return True


def _serialize_value(value):
    if value is None:
        return None
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    return value


def _format_value_for_message(value):
    if value is None or value == "":
        return "null"
    text = str(value)
    if len(text) > MAX_FIELD_VALUE_LENGTH:
        return f"{text[:MAX_FIELD_VALUE_LENGTH]}..."
    return text


def _instance_snapshot(instance):
    data = {}
    for field in instance._meta.fields:
        if not field.concrete:
            continue
        if isinstance(field, models.FileField):
            value = getattr(instance, field.name, None)
            data[field.name] = _serialize_value(value.name if value else None)
            continue

        if field.is_relation and (field.many_to_one or field.one_to_one):
            data[field.name] = _serialize_value(getattr(instance, field.attname, None))
            continue

        data[field.name] = _serialize_value(getattr(instance, field.name, None))
    return data


def _diff_snapshots(old_snapshot, new_snapshot):
    changes = []
    for key in sorted(set(old_snapshot.keys()) | set(new_snapshot.keys())):
        old_value = old_snapshot.get(key)
        new_value = new_snapshot.get(key)
        if old_value != new_value:
            changes.append({
                "field": key,
                "before": old_value,
                "after": new_value,
            })
    return changes


def _actor_from_request():
    user = get_current_user()
    if user and getattr(user, "is_authenticated", False):
        return user
    return None


def _actor_display(user):
    if not user:
        return "Systeme/Automatique"

    full_name = user.get_full_name().strip() if hasattr(user, "get_full_name") else ""
    if full_name:
        return f"{full_name} ({user.username})"
    return user.username


def _get_directors():
    from apps.employees.models import Employe

    return list(
        Employe.objects.filter(
            date_debauchage__isnull=True,
            poste__isnull=False,
        ).filter(
            Q(poste__nom_poste__icontains="directeur")
            | Q(poste__nom_poste__icontains="direction")
            | Q(poste__nom_poste__icontains="dga")
        ).select_related("user").distinct()
    )


def _ensure_director_alert_conversation(directors):
    from apps.messaging.models import Conversation, Participant

    if not directors:
        return None

    creator = directors[0]
    conversation = Conversation.objects.filter(
        type="group",
        description__startswith=ALERT_GROUP_KEY,
        archivee=False,
    ).first()

    if not conversation:
        conversation = Conversation.objects.create(
            type="group",
            nom_groupe="Alertes modifications BDD",
            description=(
                f"{ALERT_GROUP_KEY}\n"
                "Alertes automatiques sur les changements de donnees (ajout/modification/suppression)."
            ),
            createur=creator,
            archivee=False,
        )

    for director in directors:
        Participant.objects.get_or_create(
            conversation=conversation,
            employe=director,
            defaults={"est_admin": director.id == creator.id},
        )

    return conversation


def _build_message_lines(operation, model_label, object_id, actor_label, changes, full_snapshot):
    lines = [
        f"[AUDIT] {operation} sur {model_label}",
        f"Table: {model_label}",
        f"ID: {object_id}",
        f"Utilisateur: {actor_label}",
        f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    if operation == "MODIFICATION":
        lines.append("Champs modifies:")
        for item in changes[:MAX_CHANGED_FIELDS]:
            lines.append(
                f"- {item['field']}: "
                f"{_format_value_for_message(item.get('before'))} -> {_format_value_for_message(item.get('after'))}"
            )
        if len(changes) > MAX_CHANGED_FIELDS:
            lines.append(f"- ... {len(changes) - MAX_CHANGED_FIELDS} autres champs modifies")
    elif operation == "AJOUT":
        lines.append("Nouvelle ligne (contenu):")
        displayed = 0
        for field_name in sorted(full_snapshot.keys()):
            value = full_snapshot[field_name]
            if value is None or value == "":
                continue
            lines.append(f"- {field_name}: {_format_value_for_message(value)}")
            displayed += 1
            if displayed >= MAX_CREATE_DELETE_FIELDS:
                break
        if len(full_snapshot) > MAX_CREATE_DELETE_FIELDS:
            lines.append("- ... contenu tronque")
    else:
        lines.append("Ligne supprimee (contenu avant suppression):")
        displayed = 0
        for field_name in sorted(full_snapshot.keys()):
            value = full_snapshot[field_name]
            if value is None or value == "":
                continue
            lines.append(f"- {field_name}: {_format_value_for_message(value)}")
            displayed += 1
            if displayed >= MAX_CREATE_DELETE_FIELDS:
                break
        if len(full_snapshot) > MAX_CREATE_DELETE_FIELDS:
            lines.append("- ... contenu tronque")

    return "\n".join(lines)


def _write_activity_log(user, operation, model_label, object_id, details):
    try:
        # L'audit est optionnel. Le savepoint empeche une erreur d'ecriture
        # dans activity_logs de casser la transaction metier appelante.
        with transaction.atomic():
            ActivityLog.objects.create(
                log_type=(
                    "create" if operation == "AJOUT"
                    else "update" if operation == "MODIFICATION"
                    else "delete"
                ),
                user=user if user and getattr(user, "is_authenticated", False) else None,
                employe=getattr(user, "employe", None) if user and hasattr(user, "employe") else None,
                action=f"{operation} {model_label}",
                model_name=model_label,
                object_id=str(object_id),
                details=json.dumps(details, ensure_ascii=False),
            )
    except Exception:
        # Never block business operations when auditing fails.
        pass


def _extract_request_ip(request):
    if not request:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    try:
        ActivityLog.objects.create(
            log_type="login",
            user=user if getattr(user, "is_authenticated", False) else None,
            employe=getattr(user, "employe", None) if hasattr(user, "employe") else None,
            action="Connexion utilisateur",
            model_name="auth.user",
            object_id=str(getattr(user, "id", "")),
            details=json.dumps({
                "username": getattr(user, "username", ""),
                "path": getattr(request, "path", ""),
            }, ensure_ascii=False),
            ip_address=_extract_request_ip(request),
        )
    except Exception:
        pass


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    try:
        ActivityLog.objects.create(
            log_type="logout",
            user=user if user and getattr(user, "is_authenticated", False) else None,
            employe=getattr(user, "employe", None) if user and hasattr(user, "employe") else None,
            action="Deconnexion utilisateur",
            model_name="auth.user",
            object_id=str(getattr(user, "id", "")) if user else "",
            details=json.dumps({
                "username": getattr(user, "username", "") if user else "",
                "path": getattr(request, "path", "") if request else "",
            }, ensure_ascii=False),
            ip_address=_extract_request_ip(request),
        )
    except Exception:
        pass


def _publish_director_alert(user, message_body):
    try:
        from apps.messaging.models import Message

        # Comme le journal d'activite, l'alerte ne doit jamais annuler la
        # creation ou la modification qui a declenche le signal.
        with transaction.atomic():
            directors = _get_directors()
            if not directors:
                return

            conversation = _ensure_director_alert_conversation(directors)
            if not conversation:
                return

            sender = None
            if user and hasattr(user, "employe"):
                sender = user.employe

            Message.objects.create(
                conversation=conversation,
                expediteur=sender,
                type="system",
                contenu=message_body,
            )
    except Exception:
        # Never block business operations when director alerts fail.
        pass


@receiver(pre_save)
def audit_pre_save(sender, instance, **kwargs):
    if not _is_trackable(instance):
        return

    if not instance.pk:
        instance._audit_old_snapshot = None
        return

    try:
        # Cette lecture d'audit est optionnelle. Un savepoint est indispensable:
        # intercepter une DatabaseError sans rollback laisserait la transaction
        # metier dans l'etat "needs_rollback".
        with transaction.atomic():
            previous = sender.objects.filter(pk=instance.pk).first()
            instance._audit_old_snapshot = _instance_snapshot(previous) if previous else None
    except Exception:
        instance._audit_old_snapshot = None


@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    if not _is_trackable(instance):
        return

    user = _actor_from_request()
    actor_label = _actor_display(user)
    model_label = f"{instance._meta.app_label}.{instance._meta.model_name}"
    object_id = getattr(instance, "pk", None)
    new_snapshot = _instance_snapshot(instance)

    if created:
        operation = "AJOUT"
        details_payload = {
            "operation": operation,
            "model": model_label,
            "object_id": str(object_id),
            "actor": actor_label,
            "new_values": new_snapshot,
        }
        message_body = _build_message_lines(
            operation=operation,
            model_label=model_label,
            object_id=object_id,
            actor_label=actor_label,
            changes=[],
            full_snapshot=new_snapshot,
        )
    else:
        old_snapshot = getattr(instance, "_audit_old_snapshot", None) or {}
        changes = _diff_snapshots(old_snapshot, new_snapshot)
        if not changes:
            return
        operation = "MODIFICATION"
        details_payload = {
            "operation": operation,
            "model": model_label,
            "object_id": str(object_id),
            "actor": actor_label,
            "changes": changes,
        }
        message_body = _build_message_lines(
            operation=operation,
            model_label=model_label,
            object_id=object_id,
            actor_label=actor_label,
            changes=changes,
            full_snapshot={},
        )

    _write_activity_log(user, operation, model_label, object_id, details_payload)
    _publish_director_alert(user, message_body)


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    if not _is_trackable(instance):
        return

    user = _actor_from_request()
    actor_label = _actor_display(user)
    model_label = f"{instance._meta.app_label}.{instance._meta.model_name}"
    object_id = getattr(instance, "pk", None)
    snapshot = _instance_snapshot(instance)
    operation = "SUPPRESSION"

    details_payload = {
        "operation": operation,
        "model": model_label,
        "object_id": str(object_id),
        "actor": actor_label,
        "deleted_values": snapshot,
    }

    message_body = _build_message_lines(
        operation=operation,
        model_label=model_label,
        object_id=object_id,
        actor_label=actor_label,
        changes=[],
        full_snapshot=snapshot,
    )

    _write_activity_log(user, operation, model_label, object_id, details_payload)
    _publish_director_alert(user, message_body)
