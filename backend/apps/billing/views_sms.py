"""Suivi des rappels SMS de paiement : historique, relance d'un envoi, lancement manuel."""
import logging
import threading
from datetime import datetime, time, timedelta

import pytz
from .sms.config import reglage
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import connections
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.employees.permissions import has_admin_compta_access

from .models import SmsLog
from .sms import rappels

logger = logging.getLogger(__name__)
TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
PAR_PAGE = 50


def _autorise(user):
    return user.is_superuser or has_admin_compta_access(user)


def _borne(valeur, fin_de_journee=False):
    """Date AAAA-MM-JJ -> datetime aware (heure de Madagascar) ; None si vide ou invalide."""
    try:
        jour = datetime.strptime(valeur, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None
    if fin_de_journee:
        jour += timedelta(days=1)
    return TZ_MADAGASCAR.localize(datetime.combine(jour, time.min))


def _a_rappeler(today):
    """
    Abonnes joignables ayant des factures non pointees (meme selection que l'envoi), tries par
    date limite la plus proche. Retourne (lignes, total_factures, total_montant).
    """
    jours = rappels.jours_rappel()
    lignes, nb_factures, montant = [], 0, 0
    for abonne, factures in rappels.charger_factures_non_pointees(today).values():
        limites = sorted({f.date_limite for f in factures})
        prochaine = next((l for l in limites if l >= today), None)
        dates_rappel = [prochaine - timedelta(days=j) for j in jours] if prochaine else []
        lignes.append({
            'abonne': abonne,
            'factures': factures,
            'montant': sum(f.montant for f in factures),
            'limite': prochaine or limites[-1],
            'en_retard': prochaine is None,
            'prochain_rappel': min((d for d in dates_rappel if d >= today), default=None),
            'telephone_valide': bool(rappels.normaliser_numero(abonne.telephone_brut)),
        })
        nb_factures += len(factures)
        montant += lignes[-1]['montant']
    lignes.sort(key=lambda l: (l['en_retard'], l['limite']))
    return lignes, nb_factures, montant


@login_required
def historique(request):
    if not _autorise(request.user):
        return HttpResponseForbidden("Acces reserve aux administrateurs.")

    statut = request.GET.get('statut', '')
    du, au = request.GET.get('du', ''), request.GET.get('au', '')
    logs = SmsLog.objects.select_related('point_eau', 'point_eau__type_point_eau')
    if statut in dict(SmsLog.STATUT_CHOICES):
        logs = logs.filter(statut=statut)
    if _borne(du):
        logs = logs.filter(created_at__gte=_borne(du))
    if _borne(au):
        logs = logs.filter(created_at__lt=_borne(au, fin_de_journee=True))

    page = Paginator(logs.order_by('-created_at'), PAR_PAGE).get_page(request.GET.get('page'))
    filtres = request.GET.copy()
    filtres.pop('page', None)
    try:
        a_rappeler, nb_factures, montant_du = _a_rappeler(datetime.now(TZ_MADAGASCAR).date())
        erreur_apercu = ''
    except Exception as exc:  # l'apercu ne doit jamais empecher d'afficher l'historique
        logger.exception('[Rappels SMS] apercu des factures non pointees')
        a_rappeler, nb_factures, montant_du, erreur_apercu = [], 0, 0, str(exc)
    return render(request, 'billing/sms_historique.html', {
        'a_rappeler': a_rappeler, 'nb_factures_a_rappeler': nb_factures,
        'montant_a_rappeler': montant_du, 'erreur_apercu': erreur_apercu,
        'title': 'Rappels SMS de paiement',
        'page': page,
        'statuts': SmsLog.STATUT_CHOICES,
        'statut': statut, 'du': du, 'au': au,
        'filtres_qs': filtres.urlencode(),
        'dry_run': reglage('SMS_DRY_RUN'),
        'numero_mvola_configure': bool(reglage('SMS_NUMERO_MVOLA')),
        'jours_rappel': reglage('SMS_RAPPEL_JOURS'),
    })


@login_required
@require_POST
def relancer(request, pk):
    if not _autorise(request.user):
        return HttpResponseForbidden("Acces reserve aux administrateurs.")
    ligne = get_object_or_404(SmsLog, pk=pk)
    if ligne.statut not in ('echec', 'en_attente'):
        messages.info(request, "Ce SMS n'est pas en echec : rien a relancer.")
    else:
        try:
            ok, texte = rappels.relancer_groupe(ligne)
        except rappels.ExecutionEnCours:
            ok, texte = False, "Une execution des rappels est deja en cours, reessayez dans un instant."
        (messages.success if ok else messages.error)(request, texte)
    return redirect(request.META.get('HTTP_REFERER') or 'billing:sms_historique')


def _executer_en_arriere_plan():
    try:
        rappels.executer_rappels()
    except Exception:  # noqa: BLE001 - le thread ne doit jamais remonter d'exception
        logger.exception('[Rappels SMS] echec de l\'execution manuelle')
    finally:
        connections.close_all()


@login_required
@require_POST
def lancer(request):
    """
    Lance les rappels maintenant. En simulation : execution immediate et bilan affiche.
    En reel : execution en arriere-plan (la pause entre SMS depasserait le timeout de la requete),
    le suivi se fait dans le tableau. Le verrou interdit deux executions simultanees.
    """
    if not _autorise(request.user):
        return HttpResponseForbidden("Acces reserve aux administrateurs.")
    if reglage('SMS_DRY_RUN'):
        try:
            bilan = rappels.executer_rappels()
        except rappels.ExecutionEnCours:
            messages.warning(request, "Une execution des rappels est deja en cours.")
        else:
            messages.success(
                request,
                f"Simulation terminee : {bilan['simules']} simule(s), "
                f"{bilan['ignores']} ignore(s), {bilan['echecs']} echec(s).")
    elif not reglage('SMS_NUMERO_MVOLA'):
        messages.error(request, "SMS_NUMERO_MVOLA n'est pas configure : envoi reel impossible.")
    elif not rappels.verrou_libre():
        messages.warning(request, "Une execution des rappels est deja en cours.")
    else:
        threading.Thread(target=_executer_en_arriere_plan, daemon=True).start()
        messages.success(request, "Envoi lance en arriere-plan : actualisez cette page pour suivre l'avancement.")
    return redirect('billing:sms_historique')
