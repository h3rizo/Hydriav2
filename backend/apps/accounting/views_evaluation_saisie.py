"""
Vues pour l'évaluation de la qualité de la saisie comptable
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.db import models
from django.db.models import Count, Q, F, ExpressionWrapper, fields, Sum
from django.db.models.functions import TruncDate, TruncMonth, ExtractMonth, ExtractYear
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from decimal import Decimal
from .models import BaseDiameX
from apps.organization.models import Base
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
import json


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_scoped_diamex_queryset(user):
    qs = BaseDiameX.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs

    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if not gestionnaire_ids:
        return qs.none()

    allowed_progs = list(
        Base.objects.filter(organisation_id__in=gestionnaire_ids)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )
    if not allowed_progs:
        return qs.none()

    return qs.filter(prog__in=allowed_progs)


def _filter_employes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if not gestionnaire_ids:
        return queryset.none()
    return queryset.filter(base__organisation_id__in=gestionnaire_ids)


@login_required
def evaluation_saisie(request):
    """
    Page principale d'évaluation de la saisie comptable
    """
    # Obtenir la plage de dates disponibles
    date_range = _get_scoped_diamex_queryset(request.user).filter(
        date_input__isnull=False
    ).aggregate(
        min_date=models.Min('date_input'),
        max_date=models.Max('date_input')
    )

    context = {
        'date_min': date_range.get('min_date'),
        'date_max': date_range.get('max_date'),
    }

    return render(request, 'accounting/evaluation_saisie.html', context)


@login_required
def api_stats_saisie_globales(request):
    """
    API pour obtenir les statistiques globales de saisie
    """
    # Filtres
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    fichier_source = request.GET.get('fichier_source')

    # Base queryset
    qs = _get_scoped_diamex_queryset(request.user).filter(date_input__isnull=False)

    if date_debut:
        qs = qs.filter(date_input__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_input__lte=date_fin)
    if fichier_source and fichier_source != 'all':
        qs = qs.filter(fichier_source=fichier_source)

    # Statistiques globales
    total_lignes = qs.count()

    # Lignes saisies hors mois (date_input.month != date_m.month OU date_input.year != date_m.year)
    lignes_hors_mois = qs.filter(
        Q(date_m__isnull=False) &
        (
            ~Q(date_input__month=F('date_m__month')) |
            ~Q(date_input__year=F('date_m__year'))
        )
    ).count()

    # Lignes sans date_m
    lignes_sans_date_m = qs.filter(date_m__isnull=True).count()

    # Lignes conformes (saisies dans le même mois)
    lignes_conformes = total_lignes - lignes_hors_mois - lignes_sans_date_m

    # Taux de conformité
    taux_conformite = int((lignes_conformes / total_lignes * 100) if total_lignes > 0 else 0)
    taux_hors_mois = int((lignes_hors_mois / total_lignes * 100) if total_lignes > 0 else 0)

    # Nombre de jours de saisie
    jours_saisie = qs.values('date_input').distinct().count()

    # Moyenne de lignes par jour
    moyenne_jour = round(total_lignes / jours_saisie, 1) if jours_saisie > 0 else 0

    # Jour le plus productif
    jour_max = qs.values('date_input').annotate(
        count=Count('id')
    ).order_by('-count').first()

    return JsonResponse({
        'success': True,
        'stats': {
            'total_lignes': total_lignes,
            'lignes_conformes': lignes_conformes,
            'lignes_hors_mois': lignes_hors_mois,
            'lignes_sans_date_m': lignes_sans_date_m,
            'taux_conformite': taux_conformite,
            'taux_hors_mois': taux_hors_mois,
            'jours_saisie': jours_saisie,
            'moyenne_jour': moyenne_jour,
            'jour_max': {
                'date': jour_max['date_input'].strftime('%Y-%m-%d') if jour_max else None,
                'count': jour_max['count'] if jour_max else 0
            }
        }
    })


@login_required
def api_saisie_par_jour(request):
    """
    API pour obtenir le nombre de lignes saisies par jour
    """
    # Filtres
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    fichier_source = request.GET.get('fichier_source')

    # Base queryset
    qs = _get_scoped_diamex_queryset(request.user).filter(date_input__isnull=False)

    if date_debut:
        qs = qs.filter(date_input__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_input__lte=date_fin)
    if fichier_source and fichier_source != 'all':
        qs = qs.filter(fichier_source=fichier_source)

    # Grouper par jour
    saisies_jour = qs.values('date_input').annotate(
        total=Count('id'),
        conformes=Count('id', filter=Q(
            date_m__isnull=False,
            date_input__month=F('date_m__month'),
            date_input__year=F('date_m__year')
        )),
        hors_mois=Count('id', filter=Q(
            date_m__isnull=False
        ) & (
            ~Q(date_input__month=F('date_m__month')) |
            ~Q(date_input__year=F('date_m__year'))
        ))
    ).order_by('date_input')

    # Formater pour Chart.js
    labels = []
    data_total = []
    data_conformes = []
    data_hors_mois = []

    for item in saisies_jour:
        labels.append(item['date_input'].strftime('%d/%m/%Y'))
        data_total.append(item['total'])
        data_conformes.append(item['conformes'])
        data_hors_mois.append(item['hors_mois'])

    return JsonResponse({
        'success': True,
        'labels': labels,
        'datasets': {
            'total': data_total,
            'conformes': data_conformes,
            'hors_mois': data_hors_mois
        }
    })


@login_required
def api_saisie_par_mois_compta(request):
    """
    API pour obtenir les lignes saisies par mois comptable avec détail du décalage
    """
    # Filtres
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    fichier_source = request.GET.get('fichier_source')

    # Base queryset
    qs = _get_scoped_diamex_queryset(request.user).filter(date_m__isnull=False)

    if date_debut:
        qs = qs.filter(date_input__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_input__lte=date_fin)
    if fichier_source and fichier_source != 'all':
        qs = qs.filter(fichier_source=fichier_source)

    # Annoter avec le décalage en mois
    qs_annotated = qs.annotate(
        mois_comptable=TruncMonth('date_m'),
        diff_mois=ExpressionWrapper(
            (ExtractYear('date_input') - ExtractYear('date_m')) * 12 +
            (ExtractMonth('date_input') - ExtractMonth('date_m')),
            output_field=fields.IntegerField()
        )
    )

    # Grouper par mois comptable et décalage
    groupes = qs_annotated.values('mois_comptable', 'diff_mois').annotate(
        count=Count('id')
    ).order_by('mois_comptable', 'diff_mois')

    # Organiser les données
    from collections import defaultdict
    par_mois = defaultdict(lambda: {
        'conformes': 0,
        'decalage_1': 0,
        'decalage_2': 0,
        'decalage_3': 0,
        'decalage_4_plus': 0
    })

    for groupe in groupes:
        mois = groupe['mois_comptable']
        diff = groupe['diff_mois']
        count = groupe['count']

        if diff == 0:
            par_mois[mois]['conformes'] += count
        elif diff == 1:
            par_mois[mois]['decalage_1'] += count
        elif diff == 2:
            par_mois[mois]['decalage_2'] += count
        elif diff == 3:
            par_mois[mois]['decalage_3'] += count
        elif diff >= 4:
            par_mois[mois]['decalage_4_plus'] += count

    # Formater pour Chart.js (mois triés)
    mois_tries = sorted(par_mois.keys())
    labels = [m.strftime('%b %Y') for m in mois_tries]

    datasets = {
        'conformes': [par_mois[m]['conformes'] for m in mois_tries],
        'decalage_1': [par_mois[m]['decalage_1'] for m in mois_tries],
        'decalage_2': [par_mois[m]['decalage_2'] for m in mois_tries],
        'decalage_3': [par_mois[m]['decalage_3'] for m in mois_tries],
        'decalage_4_plus': [par_mois[m]['decalage_4_plus'] for m in mois_tries]
    }

    return JsonResponse({
        'success': True,
        'labels': labels,
        'datasets': datasets
    })


@login_required
def api_delai_saisie(request):
    """
    API pour obtenir la distribution des délais de saisie
    """
    # Filtres
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    fichier_source = request.GET.get('fichier_source')

    # Base queryset
    qs = _get_scoped_diamex_queryset(request.user).filter(date_m__isnull=False, date_input__isnull=False)

    if date_debut:
        qs = qs.filter(date_input__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_input__lte=date_fin)
    if fichier_source and fichier_source != 'all':
        qs = qs.filter(fichier_source=fichier_source)

    # Calculer les délais en Python pour éviter problèmes SQL
    delais = {}
    for entry in qs[:5000]:  # Limiter à 5000 pour performance
        delai_jours = (entry.date_input - entry.date_m).days
        delais[delai_jours] = delais.get(delai_jours, 0) + 1

    # Organiser par tranches
    tranches = {
        '0-7': 0,
        '8-15': 0,
        '16-30': 0,
        '31-60': 0,
        '61-90': 0,
        '90+': 0
    }

    for delai, count in delais.items():
        if delai < 0:
            continue  # Ignorer délais négatifs
        elif delai <= 7:
            tranches['0-7'] += count
        elif delai <= 15:
            tranches['8-15'] += count
        elif delai <= 30:
            tranches['16-30'] += count
        elif delai <= 60:
            tranches['31-60'] += count
        elif delai <= 90:
            tranches['61-90'] += count
        else:
            tranches['90+'] += count

    labels = list(tranches.keys())
    data = list(tranches.values())

    return JsonResponse({
        'success': True,
        'labels': labels,
        'data': data,
        'delais': delais  # Délais détaillés
    })


@login_required
def api_fichiers_sources(request):
    """
    API pour obtenir la liste des fichiers sources avec nombre de lignes
    """
    fichiers = _get_scoped_diamex_queryset(request.user).filter(
        fichier_source__isnull=False
    ).values('fichier_source').annotate(
        count=Count('id')
    ).order_by('fichier_source')

    return JsonResponse({
        'success': True,
        'fichiers': list(fichiers)
    })


@login_required
def api_top_jours_productifs(request):
    """
    API pour obtenir les 10 jours les plus productifs
    """
    # Filtres
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    fichier_source = request.GET.get('fichier_source')

    # Base queryset
    qs = _get_scoped_diamex_queryset(request.user).filter(date_input__isnull=False)

    if date_debut:
        qs = qs.filter(date_input__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_input__lte=date_fin)
    if fichier_source and fichier_source != 'all':
        qs = qs.filter(fichier_source=fichier_source)

    # Top 10 jours (avec conformite : date_input dans le meme mois que date_m)
    _hors_mois_q = Q(date_m__isnull=False) & (
        ~Q(date_input__month=F('date_m__month')) | ~Q(date_input__year=F('date_m__year'))
    )
    top_jours = qs.values('date_input').annotate(
        total=Count('id'),
        conformes=Count('id', filter=Q(
            date_m__isnull=False,
            date_input__month=F('date_m__month'),
            date_input__year=F('date_m__year'),
        )),
        hors_mois=Count('id', filter=_hors_mois_q),
    ).order_by('-total')[:10]

    data = []
    for item in top_jours:
        total = item['total'] or 0
        conf = item['conformes'] or 0
        data.append({
            'date': item['date_input'].strftime('%d/%m/%Y'),
            'total': total,
            'count': total,  # compat
            'conformes': conf,
            'hors_mois': item['hors_mois'] or 0,
            'taux_conformite': int(conf / total * 100) if total else 0,
        })

    return JsonResponse({
        'success': True,
        'top_jours': data
    })


@login_required
def api_decalage_par_mois(request):
    """
    API pour obtenir la distribution du décalage en mois
    """
    # Filtres
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    fichier_source = request.GET.get('fichier_source')

    # Base queryset
    qs = _get_scoped_diamex_queryset(request.user).filter(date_m__isnull=False)

    if date_debut:
        qs = qs.filter(date_input__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_input__lte=date_fin)
    if fichier_source and fichier_source != 'all':
        qs = qs.filter(fichier_source=fichier_source)

    # Annoter avec le décalage en mois
    qs_annotated = qs.annotate(
        diff_mois=ExpressionWrapper(
            (ExtractYear('date_input') - ExtractYear('date_m')) * 12 +
            (ExtractMonth('date_input') - ExtractMonth('date_m')),
            output_field=fields.IntegerField()
        )
    )

    # Grouper par décalage
    decalages = qs_annotated.values('diff_mois').annotate(
        count=Count('id')
    ).order_by('diff_mois')

    labels = []
    data = []

    for item in decalages:
        diff = item['diff_mois']
        if diff == 0:
            label = 'Conforme (0 mois)'
        elif diff == 1:
            label = '1 mois'
        elif diff > 0:
            label = f'{diff} mois'
        else:
            label = f'{diff} mois (antérieur)'  # Négatif

        labels.append(label)
        data.append(item['count'])

    # Distribution compacte 5 buckets (attendue par le graphe du template)
    decalages = {'decalage_0': 0, 'decalage_1': 0, 'decalage_2': 0, 'decalage_3': 0, 'decalage_4_plus': 0}
    for item in qs_annotated.values('diff_mois').annotate(count=Count('id')):
        d = item['diff_mois'] or 0
        if d <= 0:
            decalages['decalage_0'] += item['count']
        elif d == 1:
            decalages['decalage_1'] += item['count']
        elif d == 2:
            decalages['decalage_2'] += item['count']
        elif d == 3:
            decalages['decalage_3'] += item['count']
        else:
            decalages['decalage_4_plus'] += item['count']

    return JsonResponse({
        'success': True,
        'labels': labels,
        'data': data,
        'decalages': decalages,
    })


@login_required
def api_calendrier_saisie(request):
    """
    API pour obtenir un calendrier de saisie par fichier source pour un mois donné
    """
    annee = request.GET.get('annee') or datetime.now().year
    mois = request.GET.get('mois') or datetime.now().month

    # Nombre de jours dans le mois
    import calendar
    nb_jours = calendar.monthrange(int(annee), int(mois))[1]

    # Date début et fin du mois
    date_debut = datetime(int(annee), int(mois), 1).date()
    date_fin = datetime(int(annee), int(mois), nb_jours).date()

    # Récupérer tous les fichiers sources
    scoped_diamex = _get_scoped_diamex_queryset(request.user)

    fichiers = scoped_diamex.filter(
        date_input__gte=date_debut,
        date_input__lte=date_fin
    ).values('fichier_source').distinct()

    fichiers = [f['fichier_source'] for f in fichiers if f['fichier_source']]

    # Données par fichier source
    data_par_fichier = {}

    for fichier in fichiers:
        # Statistiques par jour pour ce fichier
        saisies_jour = scoped_diamex.filter(
            date_input__gte=date_debut,
            date_input__lte=date_fin,
            fichier_source=fichier
        ).values('date_input').annotate(
            total=Count('id')
        ).order_by('date_input')

        # Créer un dictionnaire date -> count
        jours_data = {}
        for item in saisies_jour:
            jours_data[item['date_input'].strftime('%Y-%m-%d')] = item['total']

        data_par_fichier[fichier] = {
            'nom': fichier,
            'jours': jours_data,
            'total_mois': sum(jours_data.values())
        }

    return JsonResponse({
        'success': True,
        'annee': int(annee),
        'mois': int(mois),
        'nb_jours': nb_jours,
        'fichiers': data_par_fichier
    })


@login_required
def api_evaluation_saisie_employe(request):
    """
    API pour obtenir les statistiques de saisie d'un employé sur une période
    Utilisé pour l'évaluation automatique des assistants administratifs
    """
    employe_id = request.GET.get('employe_id')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    if not employe_id or not date_debut or not date_fin:
        return JsonResponse({
            'success': False,
            'error': 'Paramètres manquants : employe_id, date_debut et date_fin requis'
        }, status=400)

    # Vérifier que l'employé existe
    from apps.employees.models import Employe
    try:
        employe = _filter_employes_by_scope(Employe.objects, request.user).get(id=employe_id)
    except Employe.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Employé introuvable'
        }, status=404)

    # Filtrer les saisies par date (on suppose que l'assistant admin fait toutes les saisies)
    qs = _get_scoped_diamex_queryset(request.user).filter(
        date_input__isnull=False,
        date_input__gte=date_debut,
        date_input__lte=date_fin
    )

    # Statistiques globales
    total_lignes = qs.count()

    # Lignes conformes (saisies dans le même mois comptable)
    lignes_conformes = qs.filter(
        date_m__isnull=False,
        date_input__month=F('date_m__month'),
        date_input__year=F('date_m__year')
    ).count()

    # Décalage par mois
    decalage_1_mois = qs.annotate(
        diff_mois=ExpressionWrapper(
            (ExtractYear('date_input') - ExtractYear('date_m')) * 12 +
            (ExtractMonth('date_input') - ExtractMonth('date_m')),
            output_field=fields.IntegerField()
        )
    ).filter(diff_mois=1).count()

    decalage_2_mois = qs.annotate(
        diff_mois=ExpressionWrapper(
            (ExtractYear('date_input') - ExtractYear('date_m')) * 12 +
            (ExtractMonth('date_input') - ExtractMonth('date_m')),
            output_field=fields.IntegerField()
        )
    ).filter(diff_mois=2).count()

    decalage_3_mois = qs.annotate(
        diff_mois=ExpressionWrapper(
            (ExtractYear('date_input') - ExtractYear('date_m')) * 12 +
            (ExtractMonth('date_input') - ExtractMonth('date_m')),
            output_field=fields.IntegerField()
        )
    ).filter(diff_mois=3).count()

    decalage_4_plus_mois = qs.annotate(
        diff_mois=ExpressionWrapper(
            (ExtractYear('date_input') - ExtractYear('date_m')) * 12 +
            (ExtractMonth('date_input') - ExtractMonth('date_m')),
            output_field=fields.IntegerField()
        )
    ).filter(diff_mois__gte=4).count()

    # Calcul du taux de conformité
    taux_conformite = round((lignes_conformes / total_lignes * 100), 1) if total_lignes > 0 else 0

    # Nombre de jours de saisie
    jours_saisie = qs.values('date_input').distinct().count()

    # Moyenne de lignes par jour
    moyenne_jour = round(total_lignes / jours_saisie, 1) if jours_saisie > 0 else 0

    # Calcul d'une note automatique sur 2 (comme dans le système d'évaluation)
    # Critères de notation :
    # - Taux conformité >= 90% : 2 points
    # - Taux conformité >= 70% : 1.5 points
    # - Taux conformité >= 50% : 1 point
    # - Taux conformité < 50% : 0.5 point
    # - Décalage moyen < 1.5 mois : bonus +0.5 point (max 2)

    if taux_conformite >= 90:
        note_base = 2.0
    elif taux_conformite >= 70:
        note_base = 1.5
    elif taux_conformite >= 50:
        note_base = 1.0
    else:
        note_base = 0.5

    # Calcul du décalage moyen pondéré
    total_decales = decalage_1_mois + decalage_2_mois + decalage_3_mois + decalage_4_plus_mois
    if total_decales > 0:
        decalage_moyen = (
            (decalage_1_mois * 1) +
            (decalage_2_mois * 2) +
            (decalage_3_mois * 3) +
            (decalage_4_plus_mois * 4)
        ) / total_decales
    else:
        decalage_moyen = 0

    # Bonus si décalage moyen < 1.5 mois
    if decalage_moyen < 1.5 and note_base < 2:
        note_finale = min(note_base + 0.5, 2.0)
    else:
        note_finale = note_base

    # Remarques automatiques
    remarques = []
    if taux_conformite >= 90:
        remarques.append("Excellente conformité de saisie (≥90%)")
    elif taux_conformite >= 70:
        remarques.append("Bonne conformité de saisie (≥70%)")
    elif taux_conformite >= 50:
        remarques.append("Conformité acceptable (≥50%) - À améliorer")
    else:
        remarques.append("Conformité insuffisante (<50%) - Amélioration urgente requise")

    if moyenne_jour >= 100:
        remarques.append(f"Bonne productivité : {moyenne_jour:.0f} lignes/jour en moyenne")
    elif moyenne_jour >= 50:
        remarques.append(f"Productivité satisfaisante : {moyenne_jour:.0f} lignes/jour")
    else:
        remarques.append(f"Productivité à améliorer : {moyenne_jour:.0f} lignes/jour")

    if decalage_moyen > 0:
        remarques.append(f"Décalage moyen de {decalage_moyen:.1f} mois entre date comptable et saisie")

    return JsonResponse({
        'success': True,
        'employe': {
            'id': str(employe.id),
            'nom_complet': employe.nom_complet,
            'poste': employe.poste.nom_poste if employe.poste else '-'
        },
        'periode': {
            'debut': date_debut,
            'fin': date_fin
        },
        'statistiques': {
            'total_lignes': total_lignes,
            'lignes_conformes': lignes_conformes,
            'decalage_1_mois': decalage_1_mois,
            'decalage_2_mois': decalage_2_mois,
            'decalage_3_mois': decalage_3_mois,
            'decalage_4_plus_mois': decalage_4_plus_mois,
            'taux_conformite': taux_conformite,
            'jours_saisie': jours_saisie,
            'moyenne_jour': moyenne_jour,
            'decalage_moyen': round(decalage_moyen, 1)
        },
        'evaluation_auto': {
            'note': note_finale,
            'remarques': remarques
        }
    })


@login_required
def api_evaluation_recouvrement_employe(request):
    """
    API pour obtenir les statistiques de recouvrement d'un employé sur une période
    Utilisé pour l'évaluation automatique des agents de recouvrement
    """
    employe_id = request.GET.get('employe_id')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    if not employe_id or not date_debut or not date_fin:
        return JsonResponse({
            'success': False,
            'error': 'Paramètres manquants : employe_id, date_debut et date_fin requis'
        }, status=400)

    # Vérifier que l'employé existe
    from apps.employees.models import Employe
    try:
        employe = _filter_employes_by_scope(Employe.objects, request.user).get(id=employe_id)
    except Employe.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Employé introuvable'
        }, status=404)

    # Récupérer les relevés de la période
    from apps.billing.models import Releve

    date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
    date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()

    # Tous les relevés de la période (facturés)
    releves_periode = Releve.objects.filter(
        datereleve__gte=date_debut_obj,
        datereleve__lte=date_fin_obj,
        montant__isnull=False  # Relevés facturés
    )

    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    if gestionnaire_ids is not None:
        if not gestionnaire_ids:
            releves_periode = releves_periode.none()
        else:
            releves_periode = releves_periode.filter(
                point_eau__ouvrage__modalites_gestion__gestionnaire_id__in=gestionnaire_ids,
                point_eau__ouvrage__modalites_gestion__date_fin__isnull=True
            ).distinct()

    total_releves = releves_periode.count()

    # Relevés payés (avec numeroDiameX)
    releves_payes = releves_periode.filter(numeroDiameX__isnull=False)
    nb_payes = releves_payes.count()

    # Relevés impayés
    nb_impayes = total_releves - nb_payes

    # Taux de recouvrement par nombre
    taux_recouvrement_nb = round((nb_payes / total_releves * 100), 1) if total_releves > 0 else 0

    # Montants
    montant_total = releves_periode.aggregate(
        total=Sum('montant')
    )['total'] or Decimal('0')

    montant_paye = releves_payes.aggregate(
        total=Sum('montant')
    )['total'] or Decimal('0')

    montant_impaye = montant_total - montant_paye

    # Taux de recouvrement par montant
    taux_recouvrement_montant = round((float(montant_paye) / float(montant_total) * 100), 1) if montant_total > 0 else 0

    # Délai moyen de paiement (pour les relevés payés)
    delais = []
    for releve in releves_payes:
        if releve.datepaiement and releve.datereleve:
            delai = (releve.datepaiement - releve.datereleve).days
            if delai >= 0:  # Ignorer les délais négatifs (erreurs de saisie)
                delais.append(delai)

    delai_moyen = round(sum(delais) / len(delais), 1) if delais else 0

    # Calcul d'une note automatique sur 2
    # Critères de notation :
    # - Taux recouvrement montant >= 80% : 2 points
    # - Taux recouvrement montant >= 60% : 1.5 points
    # - Taux recouvrement montant >= 40% : 1 point
    # - Taux recouvrement montant < 40% : 0.5 point
    # - Délai moyen < 30 jours : bonus +0.5 point (max 2)

    if taux_recouvrement_montant >= 80:
        note_base = 2.0
    elif taux_recouvrement_montant >= 60:
        note_base = 1.5
    elif taux_recouvrement_montant >= 40:
        note_base = 1.0
    else:
        note_base = 0.5

    # Bonus si délai moyen < 30 jours
    if delai_moyen > 0 and delai_moyen < 30 and note_base < 2:
        note_finale = min(note_base + 0.5, 2.0)
    else:
        note_finale = note_base

    # Remarques automatiques
    remarques = []

    if taux_recouvrement_montant >= 80:
        remarques.append("Excellent taux de recouvrement (≥80%)")
    elif taux_recouvrement_montant >= 60:
        remarques.append("Bon taux de recouvrement (≥60%)")
    elif taux_recouvrement_montant >= 40:
        remarques.append("Taux de recouvrement acceptable (≥40%) - À améliorer")
    else:
        remarques.append("Taux de recouvrement insuffisant (<40%) - Amélioration urgente requise")

    if nb_payes > 0:
        remarques.append(f"{nb_payes} factures recouvrées sur {total_releves} dans la période")

    if delai_moyen > 0:
        if delai_moyen < 30:
            remarques.append(f"Bon délai moyen de paiement : {delai_moyen:.0f} jours")
        elif delai_moyen < 60:
            remarques.append(f"Délai moyen de paiement acceptable : {delai_moyen:.0f} jours")
        else:
            remarques.append(f"Délai moyen de paiement à améliorer : {delai_moyen:.0f} jours")

    if montant_paye > 0:
        remarques.append(f"Montant total recouvré : {float(montant_paye):,.0f} Ar")

    return JsonResponse({
        'success': True,
        'employe': {
            'id': str(employe.id),
            'nom_complet': employe.nom_complet,
            'poste': employe.poste.nom_poste if employe.poste else '-'
        },
        'periode': {
            'debut': date_debut,
            'fin': date_fin
        },
        'statistiques': {
            'total_releves': total_releves,
            'nb_payes': nb_payes,
            'nb_impayes': nb_impayes,
            'taux_recouvrement_nb': taux_recouvrement_nb,
            'montant_total': float(montant_total),
            'montant_paye': float(montant_paye),
            'montant_impaye': float(montant_impaye),
            'taux_recouvrement_montant': taux_recouvrement_montant,
            'delai_moyen_jours': delai_moyen,
            'nb_releves_avec_delai': len(delais)
        },
        'evaluation_auto': {
            'note': note_finale,
            'remarques': remarques
        }
    })
