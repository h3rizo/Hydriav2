import re
from uuid import UUID

from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q

from apps.billing.models import ModaliteGestion, PaiementForfaitaire
from apps.employees.models import Employe
from apps.organization.models import Base

from .models import Conversation, Message, Participant


FORFAITAIRE_KEY_PREFIX = "forfait_paiement:"


def _forfait_key(paiement_id):
    return f"{FORFAITAIRE_KEY_PREFIX}{paiement_id}"


def _conversation_for_paiement(paiement):
    return Conversation.objects.filter(
        type="group",
        description__startswith=_forfait_key(paiement.id),
    ).first()


def _is_paid_in_compta(paiement):
    numero = (paiement.numeroDiameX or "").strip()
    return bool(numero)


def _safe_actor(actor):
    return actor if isinstance(actor, Employe) else None


def _first_active_employee(queryset):
    return queryset.filter(date_debauchage__isnull=True).first()


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


def _send_forfait_email(participants, paiement):
    recipients = _participant_emails(participants)
    if not recipients:
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)
    if not from_email:
        return

    ouvrage_name = (
        paiement.point_eau.ouvrage.nom_ouvrage
        if paiement.point_eau and paiement.point_eau.ouvrage
        else "Sans ouvrage"
    )
    point_label = (
        paiement.point_eau.nomabonne
        or paiement.point_eau.code_point_eau
        or paiement.point_eau.idxls
        if paiement.point_eau
        else "Point d'eau N/A"
    )
    remarque = (paiement.remarque or "").strip() or "Aucune remarque"
    date_label = paiement.date_facture.strftime("%d/%m/%Y") if paiement.date_facture else "Sans date"
    montant = f"{paiement.montant or 0} Ar"
    quantite = paiement.quantite or 0

    subject = f"[Hydria] Paiement forfaitaire a suivre - {ouvrage_name}"
    body = (
        "Un paiement forfaitaire non pointe en comptabilite est a suivre dans Hydria.\n\n"
        f"Ouvrage: {ouvrage_name}\n"
        f"Point d'eau: {point_label}\n"
        f"Date facture: {date_label}\n"
        f"Quantite: {quantite}\n"
        f"Montant: {montant}\n"
        f"Remarque: {remarque}\n\n"
        "Cette activite disparaitra des messages apres enregistrement en comptabilite (numero DiameX)."
    )
    try:
        send_mail(subject, body, from_email, recipients, fail_silently=True)
    except Exception:
        pass


def _target_base(paiement):
    if paiement.point_eau and paiement.point_eau.ouvrage:
        return Base.objects.filter(ouvrage=paiement.point_eau.ouvrage).select_related("organisation").first()
    return None


def _target_organisation(paiement):
    base = _target_base(paiement)
    return base.organisation if base and base.organisation else None


def _agent_recouvrement_for_ouvrage(paiement):
    if not (paiement.point_eau and paiement.point_eau.ouvrage):
        return None

    modalite = ModaliteGestion.objects.filter(
        ouvrage=paiement.point_eau.ouvrage,
        statut="actif",
        date_fin__isnull=True,
        modalitepaiement__in=["forfaitaire", "mixte"],
        employe__isnull=False,
    ).select_related("employe").first()
    if modalite and modalite.employe and not modalite.employe.date_debauchage:
        return modalite.employe
    return None


def _build_participants(paiement, actor=None):
    selected = {}

    def add(emp):
        if not emp:
            return
        if getattr(emp, "date_debauchage", None):
            return
        selected[str(emp.id)] = emp

    actor = _safe_actor(actor)
    add(actor)

    agent = _agent_recouvrement_for_ouvrage(paiement)
    add(agent)

    base = _target_base(paiement)
    org = _target_organisation(paiement)

    if base:
        responsable_ops = _first_active_employee(
            Employe.objects.filter(
                base=base,
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
        add(responsable_ops)

        caissiere = _first_active_employee(
            Employe.objects.filter(
                base=base,
                poste__isnull=False,
                poste__nom_poste__icontains="caiss",
            )
        )
        add(caissiere)

    if org:
        directeur_adjoint = _first_active_employee(
            Employe.objects.filter(
                base__organisation=org,
                poste__isnull=False,
            ).filter(
                (Q(poste__nom_poste__icontains="directeur") & Q(poste__nom_poste__icontains="adjoint"))
                | Q(poste__nom_poste__icontains="dga")
            )
        )
        add(directeur_adjoint)

        directeur_org = _first_active_employee(
            Employe.objects.filter(
                base__organisation=org,
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


def _forfait_context_message(paiement):
    ouvrage_name = (
        paiement.point_eau.ouvrage.nom_ouvrage
        if paiement.point_eau and paiement.point_eau.ouvrage
        else "ouvrage non defini"
    )
    point_label = (
        paiement.point_eau.nomabonne
        or paiement.point_eau.code_point_eau
        or paiement.point_eau.idxls
        if paiement.point_eau
        else "Point d'eau N/A"
    )
    date_label = paiement.date_facture.strftime("%d/%m/%Y") if paiement.date_facture else "Sans date"
    remarque = (paiement.remarque or "").strip() or "Aucune remarque"
    return (
        f"Suivi paiement forfaitaire - Ouvrage: {ouvrage_name}\n"
        f"Activite: Paiement forfaitaire ({date_label})\n"
        f"Point d'eau: {point_label}\n"
        f"Quantite: {paiement.quantite or 0}\n"
        f"Montant: {paiement.montant or 0} Ar\n"
        f"Remarque: {remarque}\n"
        "Cette activite disparaitra des messages apres pointage en comptabilite."
    )


def ensure_forfaitaire_conversation(paiement, actor=None):
    if _is_paid_in_compta(paiement):
        close_forfaitaire_conversation(
            paiement,
            actor=actor,
            reason="Paiement enregistre en comptabilite (numero DiameX). Discussion archivee.",
        )
        return None

    participants = _build_participants(paiement, actor=actor)
    if not participants:
        return None

    conversation = _conversation_for_paiement(paiement)
    if not conversation:
        creator = _safe_actor(actor) or participants[0]
        ouvrage_name = (
            paiement.point_eau.ouvrage.nom_ouvrage
            if paiement.point_eau and paiement.point_eau.ouvrage
            else "Sans ouvrage"
        )
        point_label = (
            paiement.point_eau.nomabonne
            or paiement.point_eau.code_point_eau
            if paiement.point_eau
            else "Point d'eau"
        )
        date_label = paiement.date_facture.strftime("%d/%m/%Y") if paiement.date_facture else "Sans date"
        conversation = Conversation.objects.create(
            type="group",
            nom_groupe=f"Forfaitaire - {ouvrage_name} - {point_label} - {date_label}",
            description=f"{_forfait_key(paiement.id)}\nSuivi automatique des paiements forfaitaires.",
            createur=creator,
            archivee=False,
        )

    _ensure_participants(conversation, participants, admin=_safe_actor(actor))
    if conversation.archivee:
        conversation.archivee = False
        conversation.save(update_fields=["archivee"])

    created_notice = _post_system_once(conversation, _forfait_context_message(paiement))
    if created_notice:
        _send_forfait_email(participants, paiement)
    return conversation


def close_forfaitaire_conversation(paiement, actor=None, reason=""):
    conversation = _conversation_for_paiement(paiement)
    if not conversation:
        return None
    message = reason.strip() if reason else "Paiement forfaitaire traite. Discussion archivee."
    _post_system_once(conversation, message)
    if not conversation.archivee:
        conversation.archivee = True
        conversation.save(update_fields=["archivee"])
    return conversation


def extract_forfaitaire_paiement_id(conversation):
    if not conversation or not conversation.description:
        return None
    match = re.search(rf"{FORFAITAIRE_KEY_PREFIX}([0-9a-fA-F-]{{36}})", conversation.description)
    if not match:
        return None
    try:
        return UUID(match.group(1))
    except ValueError:
        return None


def sync_forfaitaire_conversations_for_employee(employe=None, limit=800):
    qs = PaiementForfaitaire.objects.select_related(
        "point_eau",
        "point_eau__ouvrage",
    ).order_by("-date_facture", "-created_at")

    if employe and employe.base and employe.base.organisation:
        qs = qs.filter(point_eau__ouvrage__bases__organisation=employe.base.organisation).distinct()

    for paiement in qs[:limit]:
        if _is_paid_in_compta(paiement):
            close_forfaitaire_conversation(
                paiement,
                actor=None,
                reason="Paiement enregistre en comptabilite (numero DiameX). Discussion archivee.",
            )
        else:
            ensure_forfaitaire_conversation(paiement, actor=None)
