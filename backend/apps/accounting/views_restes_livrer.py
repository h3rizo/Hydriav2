"""
Suivi des restes a livrer des achats saisis (comptes 218 / 601 / 602 / 605).
"""
import json
import uuid

from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import LivraisonArticle, SaisieComptableArticle
from .saisie_articles import LivraisonError, annuler_livraison, destination_label, enregistrer_livraison
from .views_saisie_workflow import _get_current_employe, _get_scoped_saisie_queryset, _parse_date

JOURS_RETARD = 30


def _valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _scoped_articles(user):
    saisies = _get_scoped_saisie_queryset(user).filter(statut='valide')
    return (SaisieComptableArticle.objects
            .filter(saisie__in=saisies, appliquee_at__isnull=False)
            .select_related('saisie', 'saisie__base', 'designation', 'ouvrage', 'employe', 'vehicule')
            .prefetch_related('livraisons', 'livraisons__created_by'))


def _serialize_article(article, today):
    saisie = article.saisie
    age = (today - saisie.date_m).days if saisie.date_m else 0
    reste = article.quantite - article.quantite_recue
    return {
        'id': str(article.id),
        'saisie_date': saisie.date_m.isoformat() if saisie.date_m else '',
        'compte_code': saisie.compte_code or '',
        'description': saisie.description or '',
        'fournisseur': saisie.fournisseur or '',
        'base': saisie.base.nom_base if saisie.base else '',
        'designation': article.designation.nom,
        'unite': article.designation.unite or '',
        'mode': article.mode,
        'destination': destination_label({
            'destination_type': article.destination_type, 'ouvrage': article.ouvrage,
            'employe': article.employe, 'vehicule': article.vehicule}),
        'quantite': float(article.quantite),
        'quantite_recue': float(article.quantite_recue),
        'reste': float(reste),
        'age_jours': age,
        'en_retard': reste > 0 and age > JOURS_RETARD,
        'livraisons': [
            {
                'id': str(l.id), 'quantite': float(l.quantite), 'date': l.date_livraison.isoformat(),
                'remarque': l.remarque, 'annulee': l.annulee,
                'par': (l.created_by.surnom or l.created_by.nom) if l.created_by else '',
            }
            for l in article.livraisons.all()
        ],
    }


@login_required
def restes_a_livrer(request):
    return render(request, 'accounting/restes_a_livrer.html', {'jours_retard': JOURS_RETARD})


@login_required
@require_http_methods(["GET"])
def api_restes_a_livrer(request):
    """Articles avec un reste a livrer (avec ?tout=1 : aussi ceux deja livres en plusieurs fois)."""
    qs = _scoped_articles(request.user)
    if request.GET.get('tout') == '1':
        qs = qs.filter(Q(quantite_recue__lt=F('quantite')) | Q(livraisons__isnull=False)).distinct()
    else:
        qs = qs.filter(quantite_recue__lt=F('quantite'))
    mode = (request.GET.get('mode') or '').strip()
    if mode in dict(SaisieComptableArticle.MODE_CHOICES):
        qs = qs.filter(mode=mode)
    terme = (request.GET.get('q') or '').strip()
    if terme:
        qs = qs.filter(Q(designation__nom__icontains=terme) | Q(saisie__description__icontains=terme)
                       | Q(saisie__fournisseur__icontains=terme))
    base_id = (request.GET.get('base_id') or '').strip()
    if base_id and _valid_uuid(base_id):
        qs = qs.filter(saisie__base_id=base_id)
    today = timezone.localdate()
    articles = [_serialize_article(a, today) for a in qs.order_by('saisie__date_m')[:300]]
    return JsonResponse({
        'success': True,
        'articles': articles,
        'nb_en_retard': sum(1 for a in articles if a['en_retard']),
        'jours_retard': JOURS_RETARD,
    })


def _json_body(request):
    try:
        return json.loads(request.body or '{}'), None
    except json.JSONDecodeError:
        return None, JsonResponse({'success': False, 'error': 'Payload JSON invalide.'}, status=400)


@login_required
@require_http_methods(["POST"])
def api_livraison_creer(request):
    data, error = _json_body(request)
    if error:
        return error
    article = None
    if _valid_uuid(data.get('article_id')):
        article = _scoped_articles(request.user).filter(id=data['article_id']).first()
    if article is None:
        return JsonResponse({'success': False, 'error': 'Article introuvable ou hors de votre perimetre.'}, status=404)
    try:
        livraison = enregistrer_livraison(
            article.id, data.get('quantite'), _parse_date(data.get('date')), data.get('remarque'),
            _get_current_employe(request.user))
    except LivraisonError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    article = _scoped_articles(request.user).get(id=article.id)
    return JsonResponse({'success': True, 'message': 'Livraison enregistree.',
                         'article': _serialize_article(article, timezone.localdate()),
                         'livraison_id': str(livraison.id)})


@login_required
@require_http_methods(["POST"])
def api_livraison_annuler(request):
    data, error = _json_body(request)
    if error:
        return error
    livraison = None
    if _valid_uuid(data.get('livraison_id')):
        livraison = LivraisonArticle.objects.filter(
            id=data['livraison_id'], article__in=_scoped_articles(request.user)).first()
    if livraison is None:
        return JsonResponse({'success': False, 'error': 'Livraison introuvable ou hors de votre perimetre.'}, status=404)
    try:
        annuler_livraison(livraison.id, _get_current_employe(request.user))
    except LivraisonError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    article = _scoped_articles(request.user).get(id=livraison.article_id)
    return JsonResponse({'success': True, 'message': 'Livraison annulee.',
                         'article': _serialize_article(article, timezone.localdate())})
