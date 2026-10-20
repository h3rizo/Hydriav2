"""
API pour le modal de bienvenue affichant le planning des 7 prochains jours
"""

from datetime import date, timedelta, datetime
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q

import pytz

from apps.planning.models import Planning
from apps.planning.models_reparations import Reparation
from apps.employees.models import Employe, EmployeOuvrages


@login_required
@require_http_methods(["GET"])
def api_planning_7_jours(request):
    """
    API pour récupérer le planning des 7 prochains jours de l'utilisateur connecté

    Returns:
        JSON avec liste des plannings des 7 prochains jours
    """

    try:
        # Récupérer l'employé associé à l'utilisateur
        if not hasattr(request.user, 'employe') or not request.user.employe:
            return JsonResponse({
                'success': False,
                'error': 'Utilisateur non lié à un employé'
            }, status=400)

        employe = request.user.employe

        # Calculer la période des 7 prochains jours (aujourd'hui + 6 jours)
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Obtenir la date actuelle en timezone Madagascar
        maintenant_mg = timezone.now().astimezone(tz_madagascar)
        aujourd_hui = maintenant_mg.date()
        date_fin = aujourd_hui + timedelta(days=6)

        # Convertir en datetime aware pour les filtres
        aujourd_hui_dt = tz_madagascar.localize(datetime.combine(aujourd_hui, datetime.min.time()))
        date_fin_dt = tz_madagascar.localize(datetime.combine(date_fin, datetime.max.time()))

        # Récupérer les plannings de l'employé pour cette période
        plannings = Planning.objects.filter(
            employe=employe,
            date__gte=aujourd_hui_dt,
            date__lte=date_fin_dt
        ).select_related(
            'fiche_poste', 'ouvrage'
        ).order_by('date')

        # Construire la liste de résultats
        resultats = []
        for planning in plannings:
            # Convertir la date en timezone Madagascar
            if planning.date:
                if planning.date.tzinfo:
                    date_mg = planning.date.astimezone(tz_madagascar).date()
                else:
                    date_mg = tz_madagascar.localize(planning.date).date()
            else:
                date_mg = None

            # Déterminer le nom du jour de la semaine en français
            jours_semaine = {
                0: 'Lundi',
                1: 'Mardi',
                2: 'Mercredi',
                3: 'Jeudi',
                4: 'Vendredi',
                5: 'Samedi',
                6: 'Dimanche'
            }
            jour_semaine = jours_semaine.get(date_mg.weekday(), '') if date_mg else ''

            # Déterminer la classe CSS pour le badge selon l'activité
            badge_class = 'badge-info'  # Par défaut
            if planning.fiche_poste:
                activite_nom = (planning.fiche_poste.tache or '').lower()
                if 'congé' in activite_nom or 'repos' in activite_nom or 'récupération' in activite_nom:
                    badge_class = 'badge-success'
                elif 'jour férié' in activite_nom:
                    badge_class = 'badge-warning'
                elif 'réparation' in activite_nom or 'mission' in activite_nom:
                    badge_class = 'badge-error'

            resultats.append({
                'id': str(planning.id),
                'date': date_mg.strftime('%Y-%m-%d') if date_mg else None,
                'date_display': date_mg.strftime('%d/%m/%Y') if date_mg else '',
                'jour_semaine': jour_semaine,
                'activite': (planning.fiche_poste.tache or 'Aucune activité') if planning.fiche_poste else 'Aucune activité',
                'ouvrage': planning.ouvrage.nom_ouvrage if planning.ouvrage else '',
                'valide': planning.estvalide,
                'badge_class': badge_class,
                'remarque': planning.remarque or ''
            })

        # Récupérer les réparations à venir des ouvrages dont l'employé est responsable
        reparations_a_venir = []

        # Récupérer les ouvrages dont l'employé est responsable (via EmployeOuvrages)
        ouvrages_responsable = EmployeOuvrages.objects.filter(
            employe=employe
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=aujourd_hui)
        ).select_related('ouvrage').values_list('ouvrage_id', flat=True)

        if ouvrages_responsable:
            # Récupérer les réparations planifiées ou en cours pour ces ouvrages dans les 7 prochains jours
            reparations = Reparation.objects.filter(
                ouvrage_id__in=ouvrages_responsable,
                statut__in=['planifiee', 'en_cours'],
                date_prevue__gte=aujourd_hui,
                date_prevue__lte=date_fin
            ).select_related('ouvrage', 'assigne_a').order_by('date_prevue')

            for reparation in reparations:
                # Déterminer le badge selon la priorité
                priorite_badge = {
                    'basse': 'badge-info',
                    'moyenne': 'badge-warning',
                    'haute': 'badge-error',
                    'urgente': 'badge-error'
                }.get(reparation.priorite, 'badge-info')

                # Déterminer le badge selon le statut
                statut_badge = {
                    'planifiee': 'badge-warning',
                    'en_cours': 'badge-info'
                }.get(reparation.statut, 'badge-info')

                description = reparation.description or ''
                reparations_a_venir.append({
                    'id': str(reparation.id),
                    'ouvrage': reparation.ouvrage.nom_ouvrage if reparation.ouvrage else '',
                    'titre': reparation.titre or '',
                    'description': description[:100] + '...' if len(description) > 100 else description,
                    'date_prevue': reparation.date_prevue.strftime('%d/%m/%Y') if reparation.date_prevue else '',
                    'date_prevue_iso': reparation.date_prevue.strftime('%Y-%m-%d') if reparation.date_prevue else '',
                    'priorite': reparation.get_priorite_display(),
                    'priorite_badge': priorite_badge,
                    'statut': reparation.get_statut_display(),
                    'statut_badge': statut_badge,
                    'assigne_a': (reparation.assigne_a.surnom or reparation.assigne_a.nom_employe) if reparation.assigne_a else 'Non assigné'
                })

        return JsonResponse({
            'success': True,
            'plannings': resultats,
            'nb_jours': len(resultats),
            'reparations': reparations_a_venir,
            'nb_reparations': len(reparations_a_venir),
            'employe_nom': employe.surnom or employe.nom_employe,
            'periode': f"{aujourd_hui.strftime('%d/%m/%Y')} - {date_fin.strftime('%d/%m/%Y')}"
        })

    except Exception as e:
        import logging
        import traceback
        # Journalise la trace complete (sinon rien dans django-errors.log).
        logging.getLogger('django.request').exception('api_planning_7_jours a echoue')
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


NB_OUVRAGES_PROCHES_MODAL = 3


def _lire_position(request):
    """Position GPS optionnelle envoyee par le navigateur (?lat=&lng=)."""
    try:
        lat = float(request.GET['lat'])
        lng = float(request.GET['lng'])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def _attacher_distances(ouvrages_tries, position):
    """
    Ajoute 'distance_km' a chaque ouvrage (None si inconnue). Ouvrage n'a
    pas de coordonnees propres : sa position est la moyenne de celles de
    ses points d'eau geolocalises.
    """
    from django.db.models import Avg

    from apps.billing.models import PointEau
    from apps.planning.services_pointage import haversine_m

    for entree in ouvrages_tries:
        entree['distance_km'] = None
    if not position:
        return

    ouvrage_ids = [entree['ouvrage'].id for entree in ouvrages_tries]
    centres = {
        ligne['ouvrage_id']: (ligne['lat'], ligne['lng'])
        for ligne in PointEau.objects.filter(
            ouvrage_id__in=ouvrage_ids, latitude__isnull=False, longitude__isnull=False,
        ).exclude(latitude=0, longitude=0).values('ouvrage_id').annotate(
            lat=Avg('latitude'), lng=Avg('longitude'),
        )
    }
    for entree in ouvrages_tries:
        centre = centres.get(entree['ouvrage'].id)
        if centre:
            entree['distance_km'] = haversine_m(position[0], position[1], centre[0], centre[1]) / 1000


def _selectionner_ouvrages_modal(ouvrages_tries, position_connue):
    """
    Choisit les ouvrages a afficher dans le modal de bienvenue, a partir de
    la liste deja triee par criticite decroissante :
    - tous les ouvrages critiques, toujours ;
    - puis, si l'agent a partage sa position (sur le terrain), les
      NB_OUVRAGES_PROCHES_MODAL ouvrages non critiques les plus proches ;
    - sinon, les NB_OUVRAGES_PROCHES_MODAL suivants dans l'ordre de criticite.
    Retourne (ouvrages_affiches, nb_masques).
    """
    critiques = [o for o in ouvrages_tries if o['niveau_ouvrage'] == 'critique']
    autres = [o for o in ouvrages_tries if o['niveau_ouvrage'] != 'critique']

    if position_connue:
        localises = sorted((o for o in autres if o['distance_km'] is not None), key=lambda o: o['distance_km'])
        complements = localises[:NB_OUVRAGES_PROCHES_MODAL]
    else:
        complements = autres[:NB_OUVRAGES_PROCHES_MODAL]

    affiches = critiques + complements
    return affiches, len(ouvrages_tries) - len(affiches)


@login_required
@require_http_methods(["GET"])
def api_situations_attention_employe(request):
    """
    Situations a traiter (paiements non pointes + reparations echues) de
    l'employe connecte, calculees par le meme moteur que la page
    /systeme/situations-attention/ (apps.messaging.relance_engine), puis
    re-verifiees a l'instant present. Appelee separement du planning car
    le moteur se calcule a l'echelle de toute l'organisation.
    """
    from django.urls import reverse

    from apps.messaging.relance_engine import construire_regroupement_combine, trier_ouvrages_par_criticite
    from apps.messaging.relance_mailer_combine import _reverifier_eligibilite

    try:
        employe = getattr(request.user, 'employe', None)
        if not employe:
            return JsonResponse({'success': False, 'error': 'Utilisateur non lié à un employé'}, status=400)

        (
            regroupement, annee, mois, date_fin_periode,
            date_reference_reparations, _fsr, _rsr,
        ) = construire_regroupement_combine()

        vide = {
            'success': True, 'ouvrages': [], 'nb_ouvrages': 0, 'nb_masques': 0,
            'nb_factures': 0, 'nb_reparations': 0, 'montant_total': None,
            'type_destinataire': None, 'lien_consolide': None,
        }
        entree = regroupement.get(employe.id)
        if not entree:
            return JsonResponse(vide)

        ouvrages_valides = _reverifier_eligibilite(entree, date_fin_periode, date_reference_reparations)
        if not ouvrages_valides:
            return JsonResponse(vide)

        ouvrages_tries = trier_ouvrages_par_criticite(ouvrages_valides)
        position = _lire_position(request)
        _attacher_distances(ouvrages_tries, position)
        ouvrages_affiches, nb_masques = _selectionner_ouvrages_modal(ouvrages_tries, position is not None)

        lien_suivi_reparations = reverse('planning:suivi_reparations')
        nb_factures = 0
        nb_reparations = 0
        montant_total = 0
        a_un_montant = False
        resultats = []

        # Les totaux portent sur TOUS les ouvrages, meme ceux masques du modal
        for ouvrage_entree in ouvrages_tries:
            for pe_entree in ouvrage_entree['points_eau'].values():
                nb_factures += len(pe_entree['lignes'])
                for ligne in pe_entree['lignes']:
                    if ligne['montant'] is not None:
                        montant_total += float(ligne['montant'])
                        a_un_montant = True
            nb_reparations += len(ouvrage_entree['reparations'])

        for ouvrage_entree in ouvrages_affiches:
            ouvrage = ouvrage_entree['ouvrage']
            points_eau = []
            for pe_entree in sorted(ouvrage_entree['points_eau'].values(),
                                    key=lambda p: p['point_eau'].nomabonne or ''):
                pe = pe_entree['point_eau']
                montants = [float(l['montant']) for l in pe_entree['lignes'] if l['montant'] is not None]
                points_eau.append({
                    'nom': pe.nomabonne or getattr(pe, 'code_point_eau', None) or "Point d'eau",
                    'nb_factures': len(pe_entree['lignes']),
                    'montant_total': sum(montants) if montants else None,
                    'lien': reverse('core:search_detail', kwargs={'entity_type': 'point_eau', 'entity_id': str(pe.id)}),
                })

            reparations = []
            for rep_entree in sorted(ouvrage_entree['reparations'], key=lambda r: -r['jours_retard']):
                planning_rep = rep_entree['reparation']
                reparations.append({
                    'activite': getattr(planning_rep, 'activite_display', None) or 'Réparation',
                    'echeance': planning_rep.date.astimezone(pytz.timezone('Indian/Antananarivo')).strftime('%d/%m/%Y') if planning_rep.date else '',
                    'jours_retard': rep_entree['jours_retard'],
                    'niveau': rep_entree['niveau'],
                })

            resultats.append({
                'ouvrage': ouvrage.nom_ouvrage,
                'niveau': ouvrage_entree['niveau_ouvrage'],
                'distance_km': round(ouvrage_entree['distance_km'], 1) if ouvrage_entree['distance_km'] is not None else None,
                'points_eau': points_eau,
                'reparations': reparations,
                'lien_reparations': f"{lien_suivi_reparations}?ouvrage_id={ouvrage.id}",
            })

        return JsonResponse({
            'success': True,
            'type_destinataire': entree['type_destinataire'],
            'ouvrages': resultats,
            'nb_ouvrages': len(ouvrages_tries),
            'nb_masques': nb_masques,
            'position_utilisee': position is not None,
            'nb_factures': nb_factures,
            'nb_reparations': nb_reparations,
            'montant_total': montant_total if a_un_montant else None,
            'lien_consolide': reverse('messaging:commentaire_relance',
                                      kwargs={'annee': annee, 'mois': mois, 'employe_id': str(employe.id)}),
        })

    except Exception:
        import logging
        logging.getLogger('django.request').exception('api_situations_attention_employe a echoue')
        return JsonResponse({'success': False, 'error': 'Calcul des situations impossible'}, status=500)
