"""
Vues pour le suivi matriciel des congés (calendrier mensuel/annuel)
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, date, timedelta
from calendar import monthrange
from decimal import Decimal
import json
import pytz

from .models import Employe
from apps.planning.models import Planning, TypeActivite
from apps.organization.models import Base
from .utils_conges import (
    valider_dates_repos,
    valider_dates_jour_ferie,
    calculer_nb_jours as calculer_nb_jours_avec_demi
)

CONGE_ACTIVITY_NAMES = ['Congé', 'Permission (demi-journée)', 'Récupération', 'Repos']


def _planning_activity_name(planning):
    if getattr(planning, 'fiche_poste', None) and getattr(planning.fiche_poste, 'tache', None):
        return planning.fiche_poste.tache
    if getattr(planning, 'type_activite', None) and getattr(planning.type_activite, 'nomtype', None):
        return planning.type_activite.nomtype
    return ''


@login_required
def suivi_conges_matriciel(request):
    """Page de suivi matriciel des congés avec calendrier"""
    # Récupérer l'organisation de l'utilisateur
    user_org = None
    if hasattr(request.user, 'employe') and request.user.employe:
        if request.user.employe.base and request.user.employe.base.organisation:
            user_org = request.user.employe.base.organisation

    # Filtrer les bases par organisation de l'utilisateur
    bases_qs = Base.objects.all().select_related('organisation').order_by('nom_base')
    if user_org:
        bases_qs = bases_qs.filter(organisation=user_org)

    # Mois et année par défaut
    now = datetime.now()
    mois_defaut = now.month
    annee_defaut = now.year

    context = {
        'bases': bases_qs,
        'user_organisation': user_org,
        'mois_defaut': mois_defaut,
        'annee_defaut': annee_defaut,
        'title': 'Suivi Matriciel des Congés'
    }
    return render(request, 'employees/suivi_conges_matriciel.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_conges_matriciel(request):
    """API pour récupérer les données matricielles des congés"""
    try:
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Paramètres
        mois = int(request.GET.get('mois', datetime.now().month))
        annee = int(request.GET.get('annee', datetime.now().year))
        base_id = request.GET.get('base_id')
        vue = request.GET.get('vue', 'mensuel')  # 'mensuel' ou 'annuel'

        # Filtrer par organisation de l'utilisateur
        user_org = None
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                user_org = request.user.employe.base.organisation

        # Récupérer les employés actifs uniquement (date_debauchage=NULL)
        # CRITICAL: Exclure les employés avec poste "Chèque" et "Gardien"
        queryset_employes = Employe.objects.filter(
            date_debauchage__isnull=True
        ).exclude(
            poste__nom_poste__in=['Chèque', 'Gardien']
        ).select_related('poste', 'base', 'base__organisation').order_by('base__nom_base', 'poste__ordre_affichage', 'poste__nom_poste', 'nom', 'prenom')

        # Filtrer par organisation de l'utilisateur
        if user_org:
            queryset_employes = queryset_employes.filter(base__organisation=user_org)

        # Filtrer par base si spécifié
        if base_id and base_id != '':
            queryset_employes = queryset_employes.filter(base_id=base_id)

        # Déterminer la plage de dates
        if vue == 'mensuel':
            nb_jours = monthrange(annee, mois)[1]
            date_debut = datetime(annee, mois, 1)
            date_fin = datetime(annee, mois, nb_jours)
        else:  # annuel
            date_debut = datetime(annee, 1, 1)
            date_fin = datetime(annee, 12, 31)

        # Récupérer tous les plannings de la période
        plannings = Planning.objects.filter(
            employe__in=queryset_employes,
            date__gte=date_debut,
            date__lte=date_fin
        ).select_related('employe', 'type_activite', 'fiche_poste').order_by('date')

        # Organiser les plannings par employé et par date
        plannings_par_employe = {}
        for planning in plannings:
            if not planning.employe:
                continue

            employe_id = str(planning.employe.id)
            if employe_id not in plannings_par_employe:
                plannings_par_employe[employe_id] = {}

            # Convertir la date en timezone Madagascar
            date_aware = planning.date if planning.date.tzinfo else tz_madagascar.localize(planning.date)
            date_locale = date_aware.astimezone(tz_madagascar).date()
            date_str = date_locale.strftime('%Y-%m-%d')

            # Déterminer le type de jour
            activite_nom = _planning_activity_name(planning).lower()
            if not activite_nom:
                continue
            if 'cong' in activite_nom:
                if 'demi' in activite_nom:
                    type_jour = 'permission'
                else:
                    type_jour = 'conge'
            elif 'récup' in activite_nom or 'recup' in activite_nom:
                type_jour = 'recuperation'
            elif 'repos' in activite_nom:
                type_jour = 'repos'
            elif 'férié' in activite_nom or 'ferie' in activite_nom:
                type_jour = 'ferie'
            else:
                type_jour = 'travail'

            plannings_par_employe[employe_id][date_str] = {
                'type': type_jour,
                'activite': _planning_activity_name(planning),
                'valide': planning.estvalide
            }

        # Construire la liste des employés groupés par base
        employes_par_base = {}
        for employe in queryset_employes:
            base_nom = employe.base.nom_base if employe.base else 'Sans base'
            base_id_key = str(employe.base.id) if employe.base else 'none'

            if base_id_key not in employes_par_base:
                employes_par_base[base_id_key] = {
                    'base_nom': base_nom,
                    'base_id': base_id_key,
                    'employes': []
                }

            # Récupérer les plannings de cet employé
            employe_plannings = plannings_par_employe.get(str(employe.id), {})

            employes_par_base[base_id_key]['employes'].append({
                'id': str(employe.id),
                'nom': employe.nom or '',
                'prenom': employe.prenom or '',
                'surnom': employe.surnom or '',
                'nom_complet': f"{employe.surnom or employe.prenom or employe.nom or '-'}",
                'poste': employe.poste.nom_poste if employe.poste else '-',
                'plannings': employe_plannings
            })

        # Générer la liste des jours
        jours = []
        if vue == 'mensuel':
            for jour in range(1, nb_jours + 1):
                date_obj = date(annee, mois, jour)
                jours.append({
                    'numero': jour,
                    'date': date_obj.strftime('%Y-%m-%d'),
                    'nom_jour': date_obj.strftime('%a'),  # Lun, Mar, etc.
                    'est_weekend': date_obj.weekday() >= 5  # Sam=5, Dim=6
                })
        else:  # annuel - afficher mois au lieu de jours
            for m in range(1, 13):
                jours.append({
                    'numero': m,
                    'date': f"{annee}-{m:02d}",
                    'nom_jour': datetime(annee, m, 1).strftime('%b'),  # Jan, Fév, etc.
                    'est_weekend': False
                })

        return JsonResponse({
            'success': True,
            'employes_par_base': list(employes_par_base.values()),
            'jours': jours,
            'mois': mois,
            'annee': annee,
            'vue': vue,
            'mois_nom': datetime(annee, mois, 1).strftime('%B %Y') if vue == 'mensuel' else str(annee)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_creer_demande_conge_rapide(request):
    """API pour créer rapidement une demande de congé depuis le calendrier matriciel"""
    try:
        from .models_conges import DemandeConge, SoldeConge

        # Parser les données JSON
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        date_debut = data.get('date_debut')
        date_fin = data.get('date_fin')
        type_conge = data.get('type_conge')  # 'conge', 'conge_demi', 'permission', 'recuperation', 'repos', 'repos_medical', 'jour_ferie'
        motif = data.get('motif', '')
        est_demi_journee = data.get('est_demi_journee', False)

        # Validation des champs obligatoires
        if not all([employe_id, date_debut, date_fin, type_conge]):
            return JsonResponse({
                'success': False,
                'error': 'Champs obligatoires manquants'
            }, status=400)

        # Récupérer l'employé
        try:
            employe = Employe.objects.get(id=employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employé introuvable'
            }, status=404)

        # Convertir les dates
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()

        # Validations spécifiques selon le type
        try:
            if type_conge == 'repos':
                # Valider que repos respectent les règles (Sam/Dim pour non-journaliers)
                valider_dates_repos(employe, date_debut_obj, date_fin_obj)
            elif type_conge == 'jour_ferie':
                # Valider que les dates sont bien des jours fériés
                valider_dates_jour_ferie(date_debut_obj, date_fin_obj)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

        # Calculer le nombre de jours selon le type
        if type_conge in ['conge', 'conge_demi', 'repos_medical']:
            # Pour ces types, utiliser la fonction avec support demi-journée
            nb_jours = calculer_nb_jours_avec_demi(date_debut_obj, date_fin_obj, est_demi_journee and type_conge == 'conge_demi')
        elif type_conge == 'permission':
            # Permissions utilisent calcul jours ouvrés
            nb_jours_ouvres = 0
            current_date = date_debut_obj
            while current_date <= date_fin_obj:
                if current_date.weekday() < 5:  # Exclure samedi (5) et dimanche (6)
                    nb_jours_ouvres += 1
                current_date += timedelta(days=1)
            nb_jours = nb_jours_ouvres
        else:
            # Repos et jours fériés : tous les jours
            nb_jours = (date_fin_obj - date_debut_obj).days + 1

        # Récupérer le solde actuel de l'employé pour l'année et le mois en cours
        now = timezone.now()
        annee_courante = now.year
        mois_courant = now.month
        solde, created = SoldeConge.objects.get_or_create(
            employe=employe,
            annee=annee_courante,
            mois=mois_courant,
            defaults={
                'solde_conges_debut': Decimal('0'),
                'solde_conges_fin': Decimal('0'),
                'solde_permissions_debut': 0,
                'solde_permissions_fin': 0
            }
        )

        # Pour les "repos", créer directement les entrées Planning sans passer par DemandeConge
        if type_conge == 'repos':
            # Récupérer l'activité "Repos"
            type_activite_repos = TypeActivite.objects.filter(nomtype='Repos').first()
            if not type_activite_repos:
                return JsonResponse({
                    'success': False,
                    'error': 'Type d\'activité "Repos" non trouvé dans la base de données'
                }, status=500)

            # Créer les entrées Planning pour chaque jour
            plannings_crees = []
            current_date = date_debut_obj
            while current_date <= date_fin_obj:
                # Convertir la date en datetime aware
                date_planning = tz_madagascar.localize(
                    datetime.combine(current_date, datetime.min.time())
                )

                # Créer ou récupérer le planning pour cette date
                planning, created = Planning.objects.get_or_create(
                    employe=employe,
                    date=date_planning,
                    defaults={
                        'type_activite': type_activite_repos,
                        'estvalide': True  # Repos auto-validé
                    }
                )

                if created:
                    plannings_crees.append(current_date.strftime('%Y-%m-%d'))

                current_date += timedelta(days=1)

            return JsonResponse({
                'success': True,
                'message': f'Repos créé pour {len(plannings_crees)} jour(s)',
                'nb_jours': len(plannings_crees),
                'plannings_crees': plannings_crees
            })

        # Pour tous les autres types, créer une DemandeConge avec workflow
        demande = DemandeConge.objects.create(
            employe=employe,
            type_demande=type_conge,
            date_debut=date_debut_obj,
            date_fin=date_fin_obj,
            nb_jours_demandes=nb_jours,
            est_demi_journee=est_demi_journee and type_conge == 'conge_demi',
            motif=motif or f"Demande rapide depuis calendrier - {type_conge}",
            reliquat_conge_avant=solde.solde_conges_fin,
            reliquat_permission_avant=solde.solde_permissions_fin,
            statut='soumise',
            date_demande=timezone.now()
        )

        # Créer les entrées Planning pour chaque jour
        activite_map = {
            'conge': 'Congé',
            'permission': 'Permission (demi-journée)',
            'recuperation': 'Récupération',
            'repos': 'Repos'
        }
        activite_nom = activite_map.get(type_conge, 'Congé')

        # Récupérer ou créer l'activité
        type_activite, created = TypeActivite.objects.get_or_create(
            nomtype=activite_nom
        )

        # Créer un Planning pour chaque jour de la plage
        current_date = date_debut_obj
        plannings_crees = []

        while current_date <= date_fin_obj:
            # Convertir en datetime aware pour Planning
            date_planning = tz_madagascar.localize(datetime.combine(current_date, datetime.min.time()))

            # Créer le Planning
            planning, created = Planning.objects.get_or_create(
                employe=employe,
                date=date_planning,
                defaults={
                    'type_activite': type_activite,
                    'estvalide': False  # Non validé par défaut, en attente de validation
                }
            )

            if created:
                plannings_crees.append(str(current_date))

            current_date += timedelta(days=1)

        return JsonResponse({
            'success': True,
            'message': f'Demande de {type_conge} créée pour {nb_jours} jour(s). {len(plannings_crees)} entrée(s) planning créée(s).',
            'demande_id': str(demande.id),
            'nb_jours': nb_jours,
            'plannings_crees': plannings_crees
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_modifier_conge_matriciel(request):
    """API pour modifier/déplacer un congé existant depuis le calendrier matriciel"""
    try:
        from .models_conges import DemandeConge, SoldeConge

        # Parser les données JSON
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        date_debut = data.get('date_debut')
        date_fin = data.get('date_fin')
        type_conge = data.get('type_conge')
        motif = data.get('motif', '')

        # Validation
        if not all([employe_id, date_debut, date_fin, type_conge]):
            return JsonResponse({
                'success': False,
                'error': 'Champs obligatoires manquants'
            }, status=400)

        # Récupérer l'employé
        try:
            employe = Employe.objects.get(id=employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employé introuvable'
            }, status=404)

        # Convertir les dates
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()

        # Mapper le type vers l'activité
        activite_map = {
            'conge': 'Congé',
            'permission': 'Permission (demi-journée)',
            'recuperation': 'Récupération',
            'repos': 'Repos'
        }
        activite_nom = activite_map.get(type_conge, 'Congé')

        # Récupérer le type d'activité
        type_activite, _ = TypeActivite.objects.get_or_create(nomtype=activite_nom)

        # Supprimer les anciens plannings de congé pour cet employé dans la plage
        # (On suppose qu'on modifie les plannings existants dans cette période)
        Planning.objects.filter(
            employe=employe,
            date__gte=tz_madagascar.localize(datetime.combine(date_debut_obj, datetime.min.time())),
            date__lte=tz_madagascar.localize(datetime.combine(date_fin_obj, datetime.max.time())),
        ).filter(
            Q(type_activite__nomtype__in=CONGE_ACTIVITY_NAMES) |
            Q(fiche_poste__tache__in=CONGE_ACTIVITY_NAMES)
        ).delete()

        # Recréer les plannings avec le nouveau type
        current_date = date_debut_obj
        plannings_crees = []

        while current_date <= date_fin_obj:
            date_planning = tz_madagascar.localize(datetime.combine(current_date, datetime.min.time()))

            Planning.objects.create(
                employe=employe,
                date=date_planning,
                type_activite=type_activite,
                estvalide=False
            )

            plannings_crees.append(str(current_date))
            current_date += timedelta(days=1)

        return JsonResponse({
            'success': True,
            'message': f'Congé modifié : {len(plannings_crees)} jour(s) mis à jour avec type {type_conge}',
            'plannings_crees': plannings_crees
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_conge_matriciel(request):
    """API pour supprimer un congé depuis le calendrier matriciel"""
    try:
        # Parser les données JSON
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        date_str = data.get('date')

        # Validation
        if not all([employe_id, date_str]):
            return JsonResponse({
                'success': False,
                'error': 'Champs obligatoires manquants'
            }, status=400)

        # Récupérer l'employé
        try:
            employe = Employe.objects.get(id=employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employé introuvable'
            }, status=404)

        # Convertir la date
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        date_planning = tz_madagascar.localize(datetime.combine(date_obj, datetime.min.time()))

        # Chercher et supprimer le planning de congé pour cette date
        plannings = Planning.objects.filter(
            employe=employe,
            date=date_planning,
        ).filter(
            Q(type_activite__nomtype__in=CONGE_ACTIVITY_NAMES) |
            Q(fiche_poste__tache__in=CONGE_ACTIVITY_NAMES)
        )

        nb_supprimes = plannings.count()
        plannings.delete()

        if nb_supprimes > 0:
            return JsonResponse({
                'success': True,
                'message': f'Congé supprimé pour le {date_str} ({nb_supprimes} entrée(s))'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Aucun congé trouvé pour cette date'
            }, status=404)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_details_planning(request, employe_id, date_str):
    """API pour récupérer les détails d'un planning (ouvrage, activité, remarques)"""
    try:
        # Récupérer l'employé
        try:
            employe = Employe.objects.get(id=employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employé introuvable'
            }, status=404)

        # Convertir la date
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        date_planning = tz_madagascar.localize(datetime.combine(date_obj, datetime.min.time()))

        # Récupérer le planning avec les relations
        try:
            planning = Planning.objects.select_related(
                'employe',
                'type_activite',
                'fiche_poste',
                'ouvrage'
            ).get(
                employe=employe,
                date=date_planning
            )
        except Planning.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Aucun planning trouvé pour cette date'
            }, status=404)

        # Construire la réponse avec les détails
        details = {
            'employe': {
                'nom_complet': f"{employe.surnom or employe.prenom or employe.nom or '-'}",
                'poste': employe.poste.nom_poste if employe.poste else '-'
            },
            'date': date_str,
            'activite': {
                'nom': _planning_activity_name(planning) or '-',
                'description': ''
            },
            'ouvrage': {
                'nom': planning.ouvrage.nom_ouvrage if planning.ouvrage else '-',
                'type': planning.ouvrage.type_ouvrage.nom_type_ouvrage if planning.ouvrage and planning.ouvrage.type_ouvrage else ''
            } if planning.ouvrage else None,
            'remarques': planning.remarques if planning.remarques else '',
            'valide': planning.estvalide
        }

        return JsonResponse({
            'success': True,
            'details': details
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
