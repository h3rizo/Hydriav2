from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
import pytz
import re
import statistics

from apps.planning.models import PlanningDetail, Activite, Planning
from apps.billing.models import PointEau
from apps.infrastructure.models import EquipementConstitutif
from apps.organization.models import Ouvrage
from apps.geography.models import Commune


@login_required
def suivi_reparations(request):
    """Page de suivi des réparations et réhabilitations par ouvrage"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer l'organisation Soakoja par défaut
    from apps.organization.models import Organisation
    soakoja_org = Organisation.objects.filter(nom_organisation__icontains='soakoja').first()
    default_org_id = str(soakoja_org.id) if soakoja_org else ''

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    organisation_id = request.GET.get('organisation', default_org_id)  # Défaut: Soakoja
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    statut_filter = request.GET.get('statut', '')
    grading_filter = request.GET.get('grading', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    # Récupérer toutes les activités avec mots-clés réparation/réhabilitation/panne
    activites_reparation = Activite.objects.filter(
        Q(nom__icontains='réparation') |
        Q(nom__icontains='reparation') |
        Q(nom__icontains='réhabilitation') |
        Q(nom__icontains='rehabilitation') |
        Q(nom__icontains='panne')
    )

    activites_ids = list(activites_reparation.values_list('id', flat=True))

    # Récupérer les détails de planning avec ces activités
    details = PlanningDetail.objects.filter(
        planning__activite_id__in=activites_ids
    ).select_related(
        'planning',
        'planning__activite',
        'planning__employe',
        'planning__ouvrage',
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune',
        'equipement_constitutif',
        'equipement_constitutif__ouvrage'
    )

    # Appliquer les filtres géographiques
    if commune_id:
        details = details.filter(
            Q(point_eau__parcelle__village__fokontany__commune_id=commune_id) |
            Q(equipement_constitutif__ouvrage__id__in=PointEau.objects.filter(
                parcelle__village__fokontany__commune_id=commune_id
            ).values_list('ouvrage_id', flat=True))
        )

    if ouvrage_id:
        details = details.filter(
            Q(planning__ouvrage_id=ouvrage_id) |
            Q(point_eau__ouvrage_id=ouvrage_id) |
            Q(equipement_constitutif__ouvrage_id=ouvrage_id)
        )

    # Filtrer par dates si spécifiées
    if date_debut:
        details = details.filter(planning__date__gte=date_debut)
    if date_fin:
        details = details.filter(planning__date__lte=date_fin)

    # Convertir en liste et filtrer par année
    details_list = list(details.order_by('-planning__date'))
    annee_int = int(annee_filter) if annee_filter else annee_courante

    # Filtrer par année en Python avec conversion timezone
    details_filtered = []
    for detail in details_list:
        if detail.planning and detail.planning.date:
            date_aware = detail.planning.date
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_obj = date_madagascar.date()

            if date_obj.year == annee_int:
                details_filtered.append(detail)

    details_list = details_filtered

    # Grouper par ouvrage et calculer les statuts/gradings
    ouvrages_data = {}
    today = timezone.now().date()

    for detail in details_list:
        # Déterminer l'ouvrage concerné
        ouvrage = None
        if detail.planning and detail.planning.ouvrage:
            ouvrage = detail.planning.ouvrage
        elif detail.point_eau and detail.point_eau.ouvrage:
            ouvrage = detail.point_eau.ouvrage
        elif detail.equipement_constitutif and detail.equipement_constitutif.ouvrage:
            ouvrage = detail.equipement_constitutif.ouvrage

        if not ouvrage:
            continue

        if ouvrage.id not in ouvrages_data:
            ouvrages_data[ouvrage.id] = {
                'ouvrage': ouvrage,
                'commune': None,
                'reparations_passe': set(),  # Utiliser des sets pour éviter les doublons de planning_id
                'reparations_futur': set(),
                'rehabilitations_passe': set(),
                'rehabilitations_futur': set(),
                'pannes_passe': set(),
                'pannes_futur': set(),
                'details': [],
                'durees': []  # Liste des durées pour calculer moyenne/médiane
            }

            # Déterminer la commune via n'importe quel point d'eau de l'ouvrage
            point_eau_ouvrage = PointEau.objects.filter(
                ouvrage=ouvrage,
                parcelle__isnull=False,
                parcelle__village__isnull=False,
                parcelle__village__fokontany__isnull=False,
                parcelle__village__fokontany__commune__isnull=False
            ).select_related('parcelle__village__fokontany__commune').first()

            if point_eau_ouvrage:
                ouvrages_data[ouvrage.id]['commune'] = point_eau_ouvrage.parcelle.village.fokontany.commune

        # Ajouter le détail
        ouvrages_data[ouvrage.id]['details'].append(detail)

        # Calculer la durée si date de réparation existe
        if detail.planning and detail.planning.date:
            date_reparation_aware = detail.planning.date

            # Convertir en timezone Madagascar
            if date_reparation_aware.tzinfo:
                date_reparation_mg = date_reparation_aware.astimezone(tz_madagascar)
            else:
                date_reparation_mg = tz_madagascar.localize(date_reparation_aware)

            date_reparation = date_reparation_mg.date()

            # Préparer la date de signalement (convertir en date si c'est un datetime)
            if detail.planning.datesignalementactivite:
                date_signalement_raw = detail.planning.datesignalementactivite
                # Convertir en date si c'est un datetime
                if hasattr(date_signalement_raw, 'date'):
                    date_signalement = date_signalement_raw.date()
                else:
                    date_signalement = date_signalement_raw

                # Vérifier la cohérence (signalement <= réparation)
                if date_signalement > date_reparation:
                    date_signalement = date_reparation  # Incohérence, durée = 0
            else:
                # Si pas de signalement, durée = 0
                date_signalement = date_reparation

            # Calculer la durée en jours
            duree_jours = (date_reparation - date_signalement).days
            if duree_jours > 0:  # Ignorer les durées négatives ou nulles
                ouvrages_data[ouvrage.id]['durees'].append(duree_jours)

        # Analyser le type d'activité
        if detail.planning and detail.planning.date:
            date_aware = detail.planning.date
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_obj = date_madagascar.date()
            activite_nom = detail.planning.activite.nom.lower() if detail.planning.activite else ''

            is_passe = date_obj < today

            # Classifier l'activité (ajouter l'ID du planning pour éviter les doublons)
            planning_id = detail.planning.id

            if 'panne' in activite_nom:
                if is_passe:
                    ouvrages_data[ouvrage.id]['pannes_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['pannes_futur'].add(planning_id)

            if re.search(r'réhabilitation|rehabilitation', activite_nom):
                if is_passe:
                    ouvrages_data[ouvrage.id]['rehabilitations_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['rehabilitations_futur'].add(planning_id)
            elif re.search(r'réparation|reparation', activite_nom):
                if is_passe:
                    ouvrages_data[ouvrage.id]['reparations_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['reparations_futur'].add(planning_id)

    # Calculer les statuts et gradings pour chaque ouvrage
    for ouvrage_id, data in ouvrages_data.items():
        # CALCUL DU STATUT (7 niveaux par ordre de priorité)
        if data['pannes_passe']:
            data['statut'] = 'reparation_panne_effectuee'
            data['statut_label'] = 'Réparation panne effectuée'
            data['statut_badge'] = 'success'
            data['statut_icon'] = 'check-circle'
        elif data['rehabilitations_passe']:
            data['statut'] = 'rehabilitation_effectuee'
            data['statut_label'] = 'Réhabilitation effectuée'
            data['statut_badge'] = 'info'
            data['statut_icon'] = 'tools'
        elif data['reparations_passe']:
            data['statut'] = 'reparation_effectuee'
            data['statut_label'] = 'Réparation effectuée'
            data['statut_badge'] = 'primary'
            data['statut_icon'] = 'wrench'
        elif data['pannes_futur']:
            data['statut'] = 'panne_prevue'
            data['statut_label'] = 'Panne à réparer'
            data['statut_badge'] = 'error'
            data['statut_icon'] = 'exclamation-triangle'
        elif data['rehabilitations_futur']:
            data['statut'] = 'rehabilitation_prevue'
            data['statut_label'] = 'Réhabilitation prévue'
            data['statut_badge'] = 'warning'
            data['statut_icon'] = 'calendar-check'
        elif data['reparations_futur']:
            data['statut'] = 'reparation_prevue'
            data['statut_label'] = 'Réparation prévue'
            data['statut_badge'] = 'ghost'
            data['statut_icon'] = 'calendar'
        else:
            data['statut'] = 'sans_reparation'
            data['statut_label'] = 'Sans réparation'
            data['statut_badge'] = 'success'
            data['statut_icon'] = 'check-double'

        # CALCUL DU GRADING (5 niveaux par ordre de priorité)
        if not data['reparations_futur'] and not data['rehabilitations_futur'] and not data['pannes_futur']:
            data['grading'] = 'A'
            data['grading_label'] = 'A'
            data['grading_badge'] = 'success'
        elif data['rehabilitations_futur'] and data['pannes_futur']:
            data['grading'] = 'D_panne'
            data['grading_label'] = 'D Panne'
            data['grading_badge'] = 'error'
        elif data['rehabilitations_futur'] and not data['pannes_futur']:
            data['grading'] = 'D'
            data['grading_label'] = 'D'
            data['grading_badge'] = 'error'
        elif data['reparations_futur'] and data['pannes_futur']:
            data['grading'] = 'B_panne'
            data['grading_label'] = 'B Panne'
            data['grading_badge'] = 'warning'
        elif data['reparations_futur'] and not data['pannes_futur']:
            data['grading'] = 'B'
            data['grading_label'] = 'B'
            data['grading_badge'] = 'warning'
        else:
            data['grading'] = 'C'
            data['grading_label'] = 'C'
            data['grading_badge'] = 'info'

    # Filtrer par statut si spécifié
    if statut_filter:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if v.get('statut') == statut_filter}

    # Filtrer par grading si spécifié
    if grading_filter:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if v.get('grading') == grading_filter}

    # Filtrer par organisation via modalités de gestion actives
    if organisation_id and organisation_id != 'all':
        from apps.billing.models import ModaliteGestion
        ouvrages_org_ids = set(ModaliteGestion.objects.filter(
            gestionnaire_id=organisation_id,
            date_fin__isnull=True  # Modalités actives uniquement
        ).values_list('ouvrage_id', flat=True).distinct())
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if k in ouvrages_org_ids}

    # Calculer les durées moyennes et médianes
    all_durees = []
    for data in ouvrages_data.values():
        all_durees.extend(data.get('durees', []))

    duree_moyenne = round(statistics.mean(all_durees), 1) if all_durees else 0
    duree_mediane = round(statistics.median(all_durees), 1) if all_durees else 0

    # Compter les réparations/réhabilitations/pannes (passé/futur)
    total_reparations_passe = sum(len(d.get('reparations_passe', set())) for d in ouvrages_data.values())
    total_reparations_futur = sum(len(d.get('reparations_futur', set())) for d in ouvrages_data.values())
    total_rehabilitations_passe = sum(len(d.get('rehabilitations_passe', set())) for d in ouvrages_data.values())
    total_rehabilitations_futur = sum(len(d.get('rehabilitations_futur', set())) for d in ouvrages_data.values())
    total_pannes_passe = sum(len(d.get('pannes_passe', set())) for d in ouvrages_data.values())
    total_pannes_futur = sum(len(d.get('pannes_futur', set())) for d in ouvrages_data.values())

    # Calculer les statistiques
    total_ouvrages = len(ouvrages_data)
    grade_a = len([d for d in ouvrages_data.values() if d.get('grading') == 'A'])
    grade_b = len([d for d in ouvrages_data.values() if d.get('grading') == 'B'])
    grade_b_panne = len([d for d in ouvrages_data.values() if d.get('grading') == 'B_panne'])
    grade_d = len([d for d in ouvrages_data.values() if d.get('grading') == 'D'])
    grade_d_panne = len([d for d in ouvrages_data.values() if d.get('grading') == 'D_panne'])

    stats = {
        'total_ouvrages': total_ouvrages,
        'grade_a': grade_a,
        'grade_b': grade_b,
        'grade_b_panne': grade_b_panne,
        'grade_d': grade_d,
        'grade_d_panne': grade_d_panne,
        'grade_a_pct': int(round(grade_a / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_b_pct': int(round(grade_b / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_b_panne_pct': int(round(grade_b_panne / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_d_pct': int(round(grade_d / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_d_panne_pct': int(round(grade_d_panne / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'statut_panne_effectuee': len([d for d in ouvrages_data.values() if d.get('statut') == 'reparation_panne_effectuee']),
        'statut_rehabilitation_effectuee': len([d for d in ouvrages_data.values() if d.get('statut') == 'rehabilitation_effectuee']),
        'statut_reparation_effectuee': len([d for d in ouvrages_data.values() if d.get('statut') == 'reparation_effectuee']),
        'statut_panne_prevue': len([d for d in ouvrages_data.values() if d.get('statut') == 'panne_prevue']),
        'statut_rehabilitation_prevue': len([d for d in ouvrages_data.values() if d.get('statut') == 'rehabilitation_prevue']),
        'statut_reparation_prevue': len([d for d in ouvrages_data.values() if d.get('statut') == 'reparation_prevue']),
        'statut_sans_reparation': len([d for d in ouvrages_data.values() if d.get('statut') == 'sans_reparation']),
        'duree_moyenne': duree_moyenne,
        'duree_mediane': duree_mediane,
        'nb_reparations_avec_duree': len(all_durees),
        'total_reparations_passe': total_reparations_passe,
        'total_reparations_futur': total_reparations_futur,
        'total_rehabilitations_passe': total_rehabilitations_passe,
        'total_rehabilitations_futur': total_rehabilitations_futur,
        'total_pannes_passe': total_pannes_passe,
        'total_pannes_futur': total_pannes_futur,
    }

    # Listes pour les dropdowns
    communes = Commune.objects.filter(
        fokontanys__villages__parcelles__pointeau__ouvrage__isnull=False
    ).distinct().order_by('nom_commune')

    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    # Récupérer toutes les organisations pour le filtre
    organisations = Organisation.objects.all().order_by('nom_organisation')

    # Générer la liste des années disponibles
    annees_disponibles = list(range(2020, annee_courante + 2))

    # Pagination
    from django.core.paginator import Paginator
    ouvrages_list = list(ouvrages_data.values())
    page_number = request.GET.get('page', 1)
    paginator = Paginator(ouvrages_list, 50)
    page_obj = paginator.get_page(page_number)

    context = {
        'ouvrages_data': page_obj.object_list,
        'page_obj': page_obj,
        'stats': stats,
        'communes': communes,
        'ouvrages': ouvrages,
        'organisations': organisations,
        'annees_disponibles': annees_disponibles,
        'annee_filter': annee_filter,
        'organisation_filter': organisation_id,
        'commune_filter': commune_id,
        'ouvrage_filter': ouvrage_id,
        'statut_filter': statut_filter,
        'grading_filter': grading_filter,
        'date_debut': date_debut,
        'date_fin': date_fin,
    }

    return render(request, 'planning/suivi_reparations.html', context)


@login_required
def suivi_reparations_kanban(request):
    """Vue Kanban du suivi des réparations groupées par grading"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer l'organisation Soakoja par défaut
    from apps.organization.models import Organisation
    soakoja_org = Organisation.objects.filter(nom_organisation__icontains='soakoja').first()
    default_org_id = str(soakoja_org.id) if soakoja_org else ''

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    organisation_id = request.GET.get('organisation', default_org_id)  # Défaut: Soakoja
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    statut_filter = request.GET.get('statut', '')
    grading_filter = request.GET.get('grading', '')

    # Récupérer toutes les activités avec mots-clés réparation/réhabilitation/panne
    activites_reparation = Activite.objects.filter(
        Q(nom__icontains='réparation') |
        Q(nom__icontains='reparation') |
        Q(nom__icontains='réhabilitation') |
        Q(nom__icontains='rehabilitation') |
        Q(nom__icontains='panne')
    )

    activites_ids = list(activites_reparation.values_list('id', flat=True))

    # Récupérer les détails de planning avec ces activités
    details = PlanningDetail.objects.filter(
        planning__activite_id__in=activites_ids
    ).select_related(
        'planning',
        'planning__activite',
        'planning__employe',
        'planning__ouvrage',
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune',
        'equipement_constitutif',
        'equipement_constitutif__ouvrage'
    )

    # Appliquer les filtres géographiques
    if commune_id:
        details = details.filter(
            Q(point_eau__parcelle__village__fokontany__commune_id=commune_id) |
            Q(equipement_constitutif__ouvrage__id__in=PointEau.objects.filter(
                parcelle__village__fokontany__commune_id=commune_id
            ).values_list('ouvrage_id', flat=True))
        )

    if ouvrage_id:
        details = details.filter(
            Q(planning__ouvrage_id=ouvrage_id) |
            Q(point_eau__ouvrage_id=ouvrage_id) |
            Q(equipement_constitutif__ouvrage_id=ouvrage_id)
        )

    # Convertir en liste et filtrer par année
    details_list = list(details.order_by('-planning__date'))
    annee_int = int(annee_filter) if annee_filter else annee_courante

    # Filtrer par année en Python avec conversion timezone
    details_filtered = []
    for detail in details_list:
        if detail.planning and detail.planning.date:
            date_aware = detail.planning.date
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_obj = date_madagascar.date()

            if date_obj.year == annee_int:
                details_filtered.append(detail)

    details_list = details_filtered

    # Grouper par ouvrage et calculer les statuts/gradings
    ouvrages_data = {}
    today = timezone.now().date()

    for detail in details_list:
        # Déterminer l'ouvrage concerné
        ouvrage = None
        if detail.planning and detail.planning.ouvrage:
            ouvrage = detail.planning.ouvrage
        elif detail.point_eau and detail.point_eau.ouvrage:
            ouvrage = detail.point_eau.ouvrage
        elif detail.equipement_constitutif and detail.equipement_constitutif.ouvrage:
            ouvrage = detail.equipement_constitutif.ouvrage

        if not ouvrage:
            continue

        if ouvrage.id not in ouvrages_data:
            ouvrages_data[ouvrage.id] = {
                'ouvrage': ouvrage,
                'commune': None,
                'reparations_passe': set(),  # Utiliser des sets pour éviter les doublons de planning_id
                'reparations_futur': set(),
                'rehabilitations_passe': set(),
                'rehabilitations_futur': set(),
                'pannes_passe': set(),
                'pannes_futur': set(),
                'details': [],
                'durees': []  # Liste des durées pour calculer moyenne/médiane
            }

            # Déterminer la commune via n'importe quel point d'eau de l'ouvrage
            point_eau_ouvrage = PointEau.objects.filter(
                ouvrage=ouvrage,
                parcelle__isnull=False,
                parcelle__village__isnull=False,
                parcelle__village__fokontany__isnull=False,
                parcelle__village__fokontany__commune__isnull=False
            ).select_related('parcelle__village__fokontany__commune').first()

            if point_eau_ouvrage:
                ouvrages_data[ouvrage.id]['commune'] = point_eau_ouvrage.parcelle.village.fokontany.commune

        # Ajouter le détail
        ouvrages_data[ouvrage.id]['details'].append(detail)

        # Calculer la durée si date de réparation existe
        if detail.planning and detail.planning.date:
            date_reparation_aware = detail.planning.date

            # Convertir en timezone Madagascar
            if date_reparation_aware.tzinfo:
                date_reparation_mg = date_reparation_aware.astimezone(tz_madagascar)
            else:
                date_reparation_mg = tz_madagascar.localize(date_reparation_aware)

            date_reparation = date_reparation_mg.date()

            # Préparer la date de signalement (convertir en date si c'est un datetime)
            if detail.planning.datesignalementactivite:
                date_signalement_raw = detail.planning.datesignalementactivite
                # Convertir en date si c'est un datetime
                if hasattr(date_signalement_raw, 'date'):
                    date_signalement = date_signalement_raw.date()
                else:
                    date_signalement = date_signalement_raw

                # Vérifier la cohérence (signalement <= réparation)
                if date_signalement > date_reparation:
                    date_signalement = date_reparation  # Incohérence, durée = 0
            else:
                # Si pas de signalement, durée = 0
                date_signalement = date_reparation

            # Calculer la durée en jours
            duree_jours = (date_reparation - date_signalement).days
            if duree_jours > 0:  # Ignorer les durées négatives ou nulles
                ouvrages_data[ouvrage.id]['durees'].append(duree_jours)

        # Analyser le type d'activité
        if detail.planning and detail.planning.date:
            date_aware = detail.planning.date
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_obj = date_madagascar.date()
            activite_nom = detail.planning.activite.nom.lower() if detail.planning.activite else ''

            is_passe = date_obj < today

            # Classifier l'activité (ajouter l'ID du planning pour éviter les doublons)
            planning_id = detail.planning.id

            if 'panne' in activite_nom:
                if is_passe:
                    ouvrages_data[ouvrage.id]['pannes_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['pannes_futur'].add(planning_id)

            if re.search(r'réhabilitation|rehabilitation', activite_nom):
                if is_passe:
                    ouvrages_data[ouvrage.id]['rehabilitations_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['rehabilitations_futur'].add(planning_id)
            elif re.search(r'réparation|reparation', activite_nom):
                if is_passe:
                    ouvrages_data[ouvrage.id]['reparations_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['reparations_futur'].add(planning_id)

    # Calculer les statuts et gradings pour chaque ouvrage
    for ouvrage_id, data in ouvrages_data.items():
        # CALCUL DU STATUT (7 niveaux par ordre de priorité)
        if data['pannes_passe']:
            data['statut'] = 'reparation_panne_effectuee'
            data['statut_label'] = 'Réparation panne effectuée'
            data['statut_badge'] = 'success'
            data['statut_icon'] = 'check-circle'
        elif data['rehabilitations_passe']:
            data['statut'] = 'rehabilitation_effectuee'
            data['statut_label'] = 'Réhabilitation effectuée'
            data['statut_badge'] = 'info'
            data['statut_icon'] = 'tools'
        elif data['reparations_passe']:
            data['statut'] = 'reparation_effectuee'
            data['statut_label'] = 'Réparation effectuée'
            data['statut_badge'] = 'primary'
            data['statut_icon'] = 'wrench'
        elif data['pannes_futur']:
            data['statut'] = 'panne_prevue'
            data['statut_label'] = 'Panne à réparer'
            data['statut_badge'] = 'error'
            data['statut_icon'] = 'exclamation-triangle'
        elif data['rehabilitations_futur']:
            data['statut'] = 'rehabilitation_prevue'
            data['statut_label'] = 'Réhabilitation prévue'
            data['statut_badge'] = 'warning'
            data['statut_icon'] = 'calendar-check'
        elif data['reparations_futur']:
            data['statut'] = 'reparation_prevue'
            data['statut_label'] = 'Réparation prévue'
            data['statut_badge'] = 'ghost'
            data['statut_icon'] = 'calendar'
        else:
            data['statut'] = 'sans_reparation'
            data['statut_label'] = 'Sans réparation'
            data['statut_badge'] = 'success'
            data['statut_icon'] = 'check-double'

        # CALCUL DU GRADING (5 niveaux par ordre de priorité)
        if not data['reparations_futur'] and not data['rehabilitations_futur'] and not data['pannes_futur']:
            data['grading'] = 'A'
            data['grading_label'] = 'A'
            data['grading_badge'] = 'success'
        elif data['rehabilitations_futur'] and data['pannes_futur']:
            data['grading'] = 'D_panne'
            data['grading_label'] = 'D Panne'
            data['grading_badge'] = 'error'
        elif data['rehabilitations_futur'] and not data['pannes_futur']:
            data['grading'] = 'D'
            data['grading_label'] = 'D'
            data['grading_badge'] = 'error'
        elif data['reparations_futur'] and data['pannes_futur']:
            data['grading'] = 'B_panne'
            data['grading_label'] = 'B Panne'
            data['grading_badge'] = 'warning'
        elif data['reparations_futur'] and not data['pannes_futur']:
            data['grading'] = 'B'
            data['grading_label'] = 'B'
            data['grading_badge'] = 'warning'
        else:
            data['grading'] = 'C'
            data['grading_label'] = 'C'
            data['grading_badge'] = 'info'

    # Filtrer par statut si spécifié
    if statut_filter:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if v.get('statut') == statut_filter}

    # Filtrer par grading si spécifié
    if grading_filter:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if v.get('grading') == grading_filter}

    # Filtrer par organisation via modalités de gestion actives
    if organisation_id and organisation_id != 'all':
        from apps.billing.models import ModaliteGestion
        ouvrages_org_ids = set(ModaliteGestion.objects.filter(
            gestionnaire_id=organisation_id,
            date_fin__isnull=True  # Modalités actives uniquement
        ).values_list('ouvrage_id', flat=True).distinct())
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if k in ouvrages_org_ids}

    # Calculer les durées moyennes et médianes
    all_durees = []
    for data in ouvrages_data.values():
        all_durees.extend(data.get('durees', []))

    duree_moyenne = round(statistics.mean(all_durees), 1) if all_durees else 0
    duree_mediane = round(statistics.median(all_durees), 1) if all_durees else 0

    # Compter les réparations/réhabilitations/pannes (passé/futur)
    total_reparations_passe = sum(len(d.get('reparations_passe', set())) for d in ouvrages_data.values())
    total_reparations_futur = sum(len(d.get('reparations_futur', set())) for d in ouvrages_data.values())
    total_rehabilitations_passe = sum(len(d.get('rehabilitations_passe', set())) for d in ouvrages_data.values())
    total_rehabilitations_futur = sum(len(d.get('rehabilitations_futur', set())) for d in ouvrages_data.values())
    total_pannes_passe = sum(len(d.get('pannes_passe', set())) for d in ouvrages_data.values())
    total_pannes_futur = sum(len(d.get('pannes_futur', set())) for d in ouvrages_data.values())

    # Calculer les statistiques
    total_ouvrages = len(ouvrages_data)
    grade_a = len([d for d in ouvrages_data.values() if d.get('grading') == 'A'])
    grade_b = len([d for d in ouvrages_data.values() if d.get('grading') == 'B'])
    grade_b_panne = len([d for d in ouvrages_data.values() if d.get('grading') == 'B_panne'])
    grade_d = len([d for d in ouvrages_data.values() if d.get('grading') == 'D'])
    grade_d_panne = len([d for d in ouvrages_data.values() if d.get('grading') == 'D_panne'])

    stats = {
        'total_ouvrages': total_ouvrages,
        'grade_a': grade_a,
        'grade_b': grade_b,
        'grade_b_panne': grade_b_panne,
        'grade_d': grade_d,
        'grade_d_panne': grade_d_panne,
        'grade_a_pct': int(round(grade_a / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_b_pct': int(round(grade_b / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_b_panne_pct': int(round(grade_b_panne / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_d_pct': int(round(grade_d / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_d_panne_pct': int(round(grade_d_panne / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'duree_moyenne': duree_moyenne,
        'duree_mediane': duree_mediane,
        'nb_reparations_avec_duree': len(all_durees),
        'total_reparations_passe': total_reparations_passe,
        'total_reparations_futur': total_reparations_futur,
        'total_rehabilitations_passe': total_rehabilitations_passe,
        'total_rehabilitations_futur': total_rehabilitations_futur,
        'total_pannes_passe': total_pannes_passe,
        'total_pannes_futur': total_pannes_futur,
    }

    # Listes pour les dropdowns
    communes = Commune.objects.filter(
        fokontanys__villages__parcelles__pointeau__ouvrage__isnull=False
    ).distinct().order_by('nom_commune')

    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    # Récupérer toutes les organisations pour le filtre
    organisations = Organisation.objects.all().order_by('nom_organisation')

    # Générer la liste des années disponibles
    annees_disponibles = list(range(2020, annee_courante + 2))

    # Grouper par grading pour le Kanban (sans pagination)
    ouvrages_par_grading = {
        'A': [d for d in ouvrages_data.values() if d.get('grading') == 'A'],
        'B': [d for d in ouvrages_data.values() if d.get('grading') == 'B'],
        'B_panne': [d for d in ouvrages_data.values() if d.get('grading') == 'B_panne'],
        'D': [d for d in ouvrages_data.values() if d.get('grading') == 'D'],
        'D_panne': [d for d in ouvrages_data.values() if d.get('grading') == 'D_panne'],
    }

    context = {
        'ouvrages_par_grading': ouvrages_par_grading,
        'stats': stats,
        'communes': communes,
        'ouvrages': ouvrages,
        'organisations': organisations,
        'annees_disponibles': annees_disponibles,
        'annee_filter': annee_filter,
        'organisation_filter': organisation_id,
        'commune_filter': commune_id,
        'ouvrage_filter': ouvrage_id,
        'statut_filter': statut_filter,
        'grading_filter': grading_filter,
    }

    return render(request, 'planning/suivi_reparations_kanban.html', context)
