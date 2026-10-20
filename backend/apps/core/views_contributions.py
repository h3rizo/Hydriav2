"""Classement des employés selon les données qu'ils apportent dans Hydria (ContributionTerrain)."""
from datetime import date, datetime, timedelta

import pytz
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.contributions import POIDS_CATEGORIES
from apps.core.models import ContributionTerrain
from apps.employees.permissions import is_directeur_poste

tz_madagascar = pytz.timezone('Indian/Antananarivo')


def _parse_date(valeur, defaut):
    # Parsing manuel (YYYY-MM-DD) : règle timezone du projet
    try:
        a, m, j = (int(x) for x in str(valeur).split('-'))
        return date(a, m, j)
    except (ValueError, TypeError):
        return defaut


def calculer_classement(debut, fin):
    """Agrège les contributions entre deux dates incluses (jours de Madagascar).

    Le filtre par jour se fait en Python après conversion de fuseau (jamais en SQL) ;
    la requête SQL est élargie de 2 jours de chaque côté pour ne rien perdre.
    """
    marge = timedelta(days=2)
    lignes = (
        ContributionTerrain.objects
        .filter(date__gte=datetime.combine(debut, datetime.min.time(), tzinfo=pytz.utc) - marge,
                date__lt=datetime.combine(fin, datetime.min.time(), tzinfo=pytz.utc) + marge + timedelta(days=1))
        .exclude(action='suppression')
        .select_related('employe', 'user')
    )
    categories = [c for c, _ in ContributionTerrain.CATEGORIES]
    par_auteur = {}
    for ligne in lignes:
        jour = ligne.date.astimezone(tz_madagascar).date()
        if jour < debut or jour > fin:
            continue
        if ligne.employe_id:
            cle = ('e', ligne.employe_id)
            nom = ligne.employe.surnom or ligne.employe.nom or '-'
        elif ligne.user_id:
            cle = ('u', ligne.user_id)
            nom = f"{ligne.user.username} (sans fiche employé)"
        else:
            cle = ('s', 0)
            nom = 'Import / système (auteur inconnu)'
        ligne_auteur = par_auteur.setdefault(cle, {
            'nom': nom, 'par_categorie': {c: 0 for c in categories},
            'interventions': 0, 'corrections': 0, 'points': 0,
        })
        ligne_auteur['par_categorie'][ligne.categorie] = ligne_auteur['par_categorie'].get(ligne.categorie, 0) + ligne.quantite
        ligne_auteur['interventions'] += 1
        if ligne.action == 'modification':
            ligne_auteur['corrections'] += 1
        ligne_auteur['points'] += ligne.quantite * POIDS_CATEGORIES.get(ligne.categorie, 1)

    classement = sorted(par_auteur.values(), key=lambda x: (-x['points'], x['nom']))
    for rang, ligne in enumerate(classement, start=1):
        ligne['rang'] = rang
        ligne['cellules'] = [ligne['par_categorie'][c] for c in categories]
    return classement


@login_required
@require_http_methods(["GET"])
def classement_contributions(request):
    user = request.user
    if not (user.is_staff or user.is_superuser or is_directeur_poste(user)):
        return HttpResponseForbidden("Accès réservé à la direction.")

    aujourdhui = timezone.now().astimezone(tz_madagascar).date()
    debut = _parse_date(request.GET.get('debut'), aujourdhui.replace(day=1))
    fin = _parse_date(request.GET.get('fin'), aujourdhui)
    if fin < debut:
        debut, fin = fin, debut

    classement = calculer_classement(debut, fin)
    if request.GET.get('format') == 'json':
        return JsonResponse({'debut': debut.isoformat(), 'fin': fin.isoformat(),
                             'poids': POIDS_CATEGORIES, 'classement': classement})

    return render(request, 'core/classement_contributions.html', {
        'title': 'Contributions des employés',
        'debut': debut, 'fin': fin,
        'categories': ContributionTerrain.CATEGORIES,
        'poids': POIDS_CATEGORIES,
        'classement': classement,
        'total_points': sum(x['points'] for x in classement),
    })
