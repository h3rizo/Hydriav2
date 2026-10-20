"""
Vues pour les enquêtes ménages et animations WASH
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q, Avg
from django.db import connection
import json
from datetime import datetime

from .models import CaracteristiqueChantier
from .models_enquetes import Menage, EnqueteMenage, TypeAnimation, SessionAnimation, ParticipantAnimation
from apps.geography.models import Parcelle
from apps.employees.models import Employe


# ==================== MÉNAGES ====================

def menages_list(request, chantier_id):
    """Liste des ménages d'un chantier"""
    chantier = get_object_or_404(CaracteristiqueChantier, id=chantier_id)

    menages = Menage.objects.filter(chantier=chantier).select_related('parcelle')

    # Statistiques
    stats = {
        'total_menages': menages.count(),
        'total_personnes': sum(m.nombre_personnes for m in menages),
        'femmes_seules': menages.filter(est_femme_seule=True).count(),
        'avec_enquete_initiale': menages.filter(enquetes__type_enquete='initiale').distinct().count(),
        'avec_check1': menages.filter(enquetes__type_enquete='check1').distinct().count(),
        'avec_check2': menages.filter(enquetes__type_enquete='check2').distinct().count(),
    }

    # Enrichir avec statut des enquêtes
    menages_data = []
    for menage in menages:
        enquetes = {e.type_enquete: e for e in menage.enquetes.all()}
        menages_data.append({
            'menage': menage,
            'a_initiale': 'initiale' in enquetes,
            'a_check1': 'check1' in enquetes,
            'a_check2': 'check2' in enquetes,
        })

    context = {
        'chantier': chantier,
        'menages': menages_data,
        'stats': stats,
        'parcelles': Parcelle.objects.filter(
            village__in=[chantier.ouvrage.id]  # Simplification
        ).order_by('reference_parcelle')
    }

    return render(request, 'chantiers/menages_list.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def menage_create(request, chantier_id):
    """Créer un nouveau ménage"""
    try:
        chantier = get_object_or_404(CaracteristiqueChantier, id=chantier_id)
        data = json.loads(request.body)

        menage = Menage.objects.create(
            chantier=chantier,
            parcelle_id=data['parcelle_id'],
            nom_chef_menage=data['nom_chef_menage'],
            nombre_personnes=data.get('nombre_personnes', 1),
            est_femme_seule=data.get('est_femme_seule', False),
            latitude=data.get('latitude'),
            longitude=data.get('longitude')
        )

        return JsonResponse({'success': True, 'id': str(menage.id)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def menage_detail(request, menage_id):
    """Détail d'un ménage avec historique des enquêtes"""
    menage = get_object_or_404(Menage, id=menage_id)
    enquetes = menage.enquetes.all().order_by('date_enquete')

    context = {
        'menage': menage,
        'enquetes': enquetes,
        'chantier': menage.chantier,
    }

    return render(request, 'chantiers/menage_detail.html', context)


# ==================== ENQUÊTES ====================

def enquete_form(request, menage_id, type_enquete):
    """Formulaire d'enquête (initiale, check1, check2)"""
    menage = get_object_or_404(Menage, id=menage_id)

    # Vérifier si l'enquête existe déjà
    enquete = EnqueteMenage.objects.filter(menage=menage, type_enquete=type_enquete).first()

    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST.dict()

            # Données communes
            enquete_data = {
                'menage': menage,
                'type_enquete': type_enquete,
                'employe_id': data.get('employe_id'),
                'date_enquete': data.get('date_enquete', datetime.now().date()),

                # Latrine
                'menage_utilise_latrine': data.get('menage_utilise_latrine') == 'true',
                'menage_a_latrine': data.get('menage_a_latrine') == 'true',
                'type_latrine': data.get('type_latrine', 'aucune'),
                'origine_latrine': data.get('origine_latrine', ''),

                # Messages WASH
                'connait_msg_latrine': data.get('connait_msg_latrine') == 'true',
                'connait_msg_eau_potable': data.get('connait_msg_eau_potable') == 'true',
                'connait_msg_lavage_mains': data.get('connait_msg_lavage_mains') == 'true',
                'lavage_apres_selles': data.get('lavage_apres_selles') == 'true',
                'lavage_avec_savon_cendres': data.get('lavage_avec_savon_cendres') == 'true',
            }

            # Questions gestion (check2 uniquement)
            if type_enquete == 'check2':
                enquete_data.update({
                    'eau_payante': data.get('eau_payante') == 'true',
                    'paiement_pour_entretien': data.get('paiement_pour_entretien') == 'true',
                    'gestion_par_soakoja': data.get('gestion_par_soakoja') == 'true',
                    'coupure_si_non_paiement': data.get('coupure_si_non_paiement') == 'true',
                    'appel_soakoja_probleme': data.get('appel_soakoja_probleme') == 'true',
                })

            if enquete:
                # Mise à jour
                for key, value in enquete_data.items():
                    if key not in ['menage', 'type_enquete']:
                        setattr(enquete, key, value)
                enquete.save()
            else:
                # Création
                enquete = EnqueteMenage.objects.create(**enquete_data)

            return JsonResponse({
                'success': True,
                'id': str(enquete.id),
                'score_wash': enquete.score_messages_wash,
                'score_gestion': enquete.score_gestion_ouvrage
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    # GET - afficher le formulaire
    employes = Employe.objects.filter(date_debauchage__isnull=True).order_by('nom')

    context = {
        'menage': menage,
        'chantier': menage.chantier,
        'type_enquete': type_enquete,
        'enquete': enquete,
        'employes': employes,
        'type_choices': EnqueteMenage.TYPE_LATRINE_CHOICES,
        'origine_choices': EnqueteMenage.ORIGINE_LATRINE_CHOICES,
        'today': datetime.now(),
    }

    return render(request, 'chantiers/enquete_form.html', context)


# ==================== ANIMATIONS ====================

def animations_list(request, chantier_id):
    """Liste des sessions d'animation d'un chantier"""
    chantier = get_object_or_404(CaracteristiqueChantier, id=chantier_id)

    sessions = SessionAnimation.objects.filter(chantier=chantier).select_related(
        'type_animation', 'animateur'
    ).order_by('-date_animation')

    # Statistiques globales
    stats = {
        'total_sessions': sessions.count(),
        'types_animation': TypeAnimation.objects.count(),
    }

    # Enrichir avec stats par session
    sessions_data = []
    for session in sessions:
        sessions_data.append({
            'session': session,
            'nb_participants': session.participants.count(),
            'nb_presents': session.participants.filter(etait_present=True).count(),
            'taux_presence': session.taux_presence,
        })

    context = {
        'chantier': chantier,
        'sessions': sessions_data,
        'stats': stats,
        'types_animation': TypeAnimation.objects.all(),
        'employes': Employe.objects.filter(date_debauchage__isnull=True).order_by('nom'),
    }

    return render(request, 'chantiers/animations_list.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def animation_create(request, chantier_id):
    """Créer une session d'animation"""
    try:
        chantier = get_object_or_404(CaracteristiqueChantier, id=chantier_id)
        data = json.loads(request.body)

        session = SessionAnimation.objects.create(
            chantier=chantier,
            type_animation_id=data['type_animation_id'],
            animateur_id=data['animateur_id'],
            date_animation=data['date_animation'],
            lieu=data.get('lieu', '')
        )

        return JsonResponse({'success': True, 'id': str(session.id)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def animation_participants(request, session_id):
    """Gérer les participants d'une session"""
    session = get_object_or_404(SessionAnimation, id=session_id)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            # Ajouter un participant
            participant = ParticipantAnimation.objects.create(
                session=session,
                menage_id=data['menage_id'],
                nom_participant=data['nom_participant'],
                sexe=data['sexe'],
                etait_present=False  # Par défaut absent, sera mis à jour lors du pointage
            )

            return JsonResponse({'success': True, 'id': str(participant.id)})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    # GET - liste des participants
    participants = session.participants.select_related('menage').all()
    menages = Menage.objects.filter(chantier=session.chantier).order_by('nom_chef_menage')

    context = {
        'session': session,
        'chantier': session.chantier,
        'participants': participants,
        'menages': menages,
        'nb_presents': participants.filter(etait_present=True).count(),
    }

    return render(request, 'chantiers/animation_participants.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def animation_presence(request, session_id):
    """Cocher la présence des participants"""
    try:
        session = get_object_or_404(SessionAnimation, id=session_id)
        data = json.loads(request.body)

        # data = {'participant_id': bool}
        for participant_id, present in data.items():
            ParticipantAnimation.objects.filter(
                id=participant_id,
                session=session
            ).update(etait_present=present)

        return JsonResponse({
            'success': True,
            'nb_presents': session.participants.filter(etait_present=True).count()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ==================== DASHBOARD ====================

def chantier_dashboard(request, chantier_id):
    """Dashboard d'évolution pour un chantier"""
    chantier = get_object_or_404(CaracteristiqueChantier, id=chantier_id)

    # Statistiques ménages
    menages = Menage.objects.filter(chantier=chantier)
    total_menages = menages.count()
    total_personnes = sum(m.nombre_personnes for m in menages)

    # Évolution latrines
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            type_enquete,
            COUNT(CASE WHEN menage_a_latrine THEN 1 END) as avec_latrine,
            COUNT(CASE WHEN type_latrine = 'amelioree' THEN 1 END) as latrines_ameliorees,
            COUNT(CASE WHEN origine_latrine = 'nouvelle' THEN 1 END) as nouvelles_latrines,
            AVG(connait_msg_latrine::int + connait_msg_eau_potable::int + connait_msg_lavage_mains::int + lavage_apres_selles::int + lavage_avec_savon_cendres::int) as score_wash_moyen
        FROM enquetes_menages e
        JOIN menages m ON e.menage_id = m.id
        WHERE m.chantier_id = %s
        GROUP BY type_enquete
        ORDER BY
            CASE type_enquete
                WHEN 'initiale' THEN 1
                WHEN 'check1' THEN 2
                WHEN 'check2' THEN 3
            END
    """, [str(chantier_id)])

    evolution_enquetes = cursor.fetchall()

    # Statistiques animations
    sessions = SessionAnimation.objects.filter(chantier=chantier)
    participants_total = ParticipantAnimation.objects.filter(session__chantier=chantier)

    # Répartition par nombre d'animations assistées
    cursor.execute("""
        SELECT
            COUNT(DISTINCT CASE WHEN nb = 0 THEN participant_key END) as zero_animation,
            COUNT(DISTINCT CASE WHEN nb = 1 THEN participant_key END) as une_animation,
            COUNT(DISTINCT CASE WHEN nb = 2 THEN participant_key END) as deux_animations,
            COUNT(DISTINCT CASE WHEN nb >= 3 THEN participant_key END) as trois_plus_animations
        FROM (
            SELECT
                CONCAT(menage_id, '-', nom_participant) as participant_key,
                SUM(CASE WHEN etait_present THEN 1 ELSE 0 END) as nb
            FROM participants_animations p
            JOIN sessions_animations s ON p.session_id = s.id
            WHERE s.chantier_id = %s
            GROUP BY participant_key
        ) sub
    """, [str(chantier_id)])

    repartition_animations = cursor.fetchone()

    context = {
        'chantier': chantier,
        'total_menages': total_menages,
        'total_personnes': total_personnes,
        'evolution_enquetes': evolution_enquetes,
        'total_sessions': sessions.count(),
        'nb_femmes_total': participants_total.filter(sexe='F').count(),
        'nb_hommes_total': participants_total.filter(sexe='M').count(),
        'nb_femmes_presentes': participants_total.filter(sexe='F', etait_present=True).count(),
        'nb_hommes_presents': participants_total.filter(sexe='M', etait_present=True).count(),
        'repartition_animations': {
            'zero': repartition_animations[0] if repartition_animations else 0,
            'une': repartition_animations[1] if repartition_animations else 0,
            'deux': repartition_animations[2] if repartition_animations else 0,
            'trois_plus': repartition_animations[3] if repartition_animations else 0,
        }
    }

    return render(request, 'chantiers/chantier_dashboard.html', context)
