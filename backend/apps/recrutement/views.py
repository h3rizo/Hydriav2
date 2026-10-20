"""
Vues pour le systeme de recrutement et tests de candidats
"""
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction
from django.utils.crypto import get_random_string
import logging
import json

from .models import CandidatPreconfigure, Candidat, QuestionTest, SessionTest, ReponseCandidat
from apps.employees.models import Poste

logger = logging.getLogger(__name__)


def _get_candidate_session_for_user(user, session_id):
    return SessionTest.objects.filter(
        id=session_id,
        candidat__user=user,
    ).first()


def _log_missing_candidate_session(request, session_id, action):
    logger.warning(
        "Recrutement session introuvable",
        extra={
            'action': action,
            'session_id': str(session_id),
            'user_id': getattr(request.user, 'id', None),
            'username': getattr(request.user, 'username', ''),
            'path': request.path,
            'method': request.method,
        }
    )


def _creer_session_test(candidat):
    if not candidat.poste_souhaite_id:
        raise ValueError("Aucun poste n'est associe a votre candidature.")

    questions = QuestionTest.objects.filter(
        poste=candidat.poste_souhaite,
        active=True
    ).order_by('ordre')

    if not questions.exists():
        raise ValueError('Aucune question nâ€™est disponible pour ce poste.')

    session = SessionTest.objects.create(
        candidat=candidat,
        score_total=sum(q.points for q in questions)
    )

    session.demarrer()

    for question in questions:
        ReponseCandidat.objects.create(
            session=session,
            question=question,
            reponse_donnee=''
        )

    candidat.statut = 'test_en_cours'
    candidat.save(update_fields=['statut'])
    return session


def inscription_candidat(request):
    """
    Page d'inscription pour les candidats.
    Workflow:
    1. Candidat entre son email
    2. Vérification de préconfiguration (admin)
    3. Si préconfiguré: formulaire complet
    4. Sinon: message d'erreur
    """
    # Vérifier si email en paramètre GET
    email_param = request.GET.get('email')
    candidat_preconfig = None
    inscription_initial = {}

    if email_param:
        try:
            candidat_preconfig = CandidatPreconfigure.objects.select_related('poste').get(
                email=email_param,
                test_complete=False
            )
            linked_candidat = candidat_preconfig.candidat or Candidat.objects.filter(email__iexact=email_param).first()
            inscription_initial = {
                'nom': (linked_candidat.nom if linked_candidat else '') or candidat_preconfig.nom or '',
                'prenom': (linked_candidat.prenom if linked_candidat else '') or candidat_preconfig.prenom or '',
                'telephone': (linked_candidat.telephone if linked_candidat else '') or '',
                'experience': (
                    (linked_candidat.experience if linked_candidat else '') or
                    candidat_preconfig.experience_poste or
                    candidat_preconfig.autre_experience or
                    ''
                ),
                'formation': (linked_candidat.formation if linked_candidat else '') or candidat_preconfig.formation or '',
                'cv_url': (
                    linked_candidat.cv.url if linked_candidat and linked_candidat.cv else
                    candidat_preconfig.cv.url if candidat_preconfig.cv else
                    ''
                ),
                'lettre_url': (
                    linked_candidat.lettre_motivation.url if linked_candidat and linked_candidat.lettre_motivation else
                    candidat_preconfig.lettre_motivation.url if candidat_preconfig.lettre_motivation else
                    ''
                ),
            }
        except CandidatPreconfigure.DoesNotExist:
            messages.error(request,
                "Votre email n'est pas enregistrédans notre systeme. "
                "Veuillez contacter l'administration des ressources humaines."
            )

    if request.method == 'POST':
        try:
            email = request.POST.get('email')

            # Vérifier la préconfiguration
            try:
                preconfig = CandidatPreconfigure.objects.select_related('poste').get(
                    email=email,
                    test_complete=False
                )
            except CandidatPreconfigure.DoesNotExist:
                messages.error(request,
                    "Votre email n'est pas autorisé. Contactez l'administration RH."
                )
                return redirect('/recrutement/inscription/')

            # Vérifier si l'utilisateur existe déjÃ 
            existing_user = User.objects.filter(username=email).first()
            if existing_user:
                try:
                    candidat = existing_user.candidat
                except Candidat.DoesNotExist:
                    messages.error(request,
                        "Un compte existe déjÃ  pour cet email mais aucun profil candidat n'est associé. "
                        "Contactez l'administration RH."
                    )
                    return redirect('/recrutement/inscription/')

                if not preconfig.candidat:
                    preconfig.candidat = candidat
                    preconfig.save(update_fields=['candidat'])

                existing_user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, existing_user)
                messages.info(request, 'Connexion automatique établie pour votre compte existant.')

                session_en_cours = SessionTest.objects.filter(
                    candidat=candidat,
                    statut='en_cours'
                ).first()
                if session_en_cours:
                    return redirect('recrutement:test', session_id=session_en_cours.id)

                profile_complete = all([
                    candidat.date_naissance,
                    candidat.adresse,
                    candidat.cv,
                    candidat.lettre_motivation
                ])
                if not profile_complete:
                    return redirect('recrutement:profil')
                return redirect('/recrutement/dashboard/')

            # Créer l'utilisateur (sans mot de passe au départ)
            # Le mot de passe sera généré automatiquement ou envoyé par email
            from django.utils.crypto import get_random_string

            random_password = get_random_string(12)
            user = User.objects.create_user(
                username=email,
                email=email,
                password=random_password,
                first_name=request.POST.get('prenom'),
                last_name=request.POST.get('nom')
            )

            # Créer le candidat
            candidat = Candidat.objects.create(
                user=user,
                nom=request.POST.get('nom') or preconfig.nom,
                prenom=request.POST.get('prenom') or preconfig.prenom,
                email=email,
                telephone=request.POST.get('telephone'),
                poste_souhaite=preconfig.poste,
                experience=request.POST.get('experience') or preconfig.experience_poste or preconfig.autre_experience,
                formation=request.POST.get('formation') or preconfig.formation,
                date_naissance=preconfig.date_naissance,
                adresse=preconfig.domicile,
                cv=request.FILES.get('cv') or preconfig.cv,
                lettre_motivation=request.FILES.get('lettre_motivation') or preconfig.lettre_motivation
            )

            # Lier Ã  la préconfiguration
            preconfig.candidat = candidat
            if preconfig.screening_statut not in {'invite_test', 'test_complete'}:
                preconfig.screening_statut = 'invite_test'
            preconfig.invite_test_envoyee = True
            preconfig.save(update_fields=['candidat', 'screening_statut', 'invite_test_envoyee'])

            # Connexion automatique
            login(request, user)

            messages.success(request,
                'Inscription réussie ! Vous pouvez maintenant passer le test.'
            )
            return redirect('/recrutement/dashboard/')

        except Exception as e:
            messages.error(request, f'Erreur lors de l\'inscription : {str(e)}')
            return redirect('/recrutement/inscription/')

    return render(request, 'recrutement/inscription.html', {
        'email_preconfigure': candidat_preconfig.email if candidat_preconfig else None,
        'poste_preconfigure': candidat_preconfig.poste if candidat_preconfig else None,
        'inscription_initial': inscription_initial,
    })


@login_required
def profil_candidat(request):
    try:
        candidat = request.user.candidat
    except Candidat.DoesNotExist:
        return redirect('recrutement:inscription')

    if request.method == 'POST':
        try:
            nom = request.POST.get('nom', '').strip()
            prenom = request.POST.get('prenom', '').strip()
            formation = request.POST.get('formation', '').strip()
            experience = request.POST.get('experience', '').strip()
            adresse = request.POST.get('adresse', '').strip()
            date_naissance = request.POST.get('date_naissance', '')

            if not all([nom, prenom, formation, experience, adresse, date_naissance]):
                raise ValueError('Tous les champs sont obligatoires.')

            if not candidat.cv and 'cv' not in request.FILES:
                raise ValueError('Veuillez téléverser votre CV.')
            if not candidat.lettre_motivation and 'lettre_motivation' not in request.FILES:
                raise ValueError('Veuillez téléverser votre lettre de motivation.')

            candidat.nom = nom
            candidat.prenom = prenom
            candidat.formation = formation
            candidat.experience = experience
            candidat.adresse = adresse
            candidat.date_naissance = datetime.strptime(date_naissance, '%Y-%m-%d').date()
            candidat.telephone = request.POST.get('telephone', candidat.telephone)

            if 'cv' in request.FILES:
                candidat.cv = request.FILES['cv']
            if 'lettre_motivation' in request.FILES:
                candidat.lettre_motivation = request.FILES['lettre_motivation']

            with transaction.atomic():
                candidat.save()
                existing_session = SessionTest.objects.filter(
                    candidat=candidat,
                    statut__in=['termine', 'expire']
                ).first()

                if existing_session:
                    messages.error(request, 'Vous avez déjÃ  passé le test.')
                    return redirect('recrutement:resultats', session_id=existing_session.id)

                session_en_cours = SessionTest.objects.filter(
                    candidat=candidat,
                    statut='en_cours'
                ).first()

                if session_en_cours:
                    return redirect('recrutement:test', session_id=session_en_cours.id)

                session = _creer_session_test(candidat)

            messages.success(request, 'Informations enregistrées. Le test démarre maintenant.')
            return redirect('recrutement:test', session_id=session.id)

        except ValueError as ve:
            messages.error(request, str(ve))
        except Exception as e:
            logger.exception(
                "Erreur soumission profil candidat",
                extra={
                    'user_id': getattr(request.user, 'id', None),
                    'candidat_id': str(candidat.id) if getattr(candidat, 'id', None) else None,
                    'path': request.path,
                    'method': request.method,
                }
            )
            messages.error(request, f'Erreur lors de la soumission : {str(e)}')

    return render(request, 'recrutement/profil.html', {
        'candidat': candidat
    })


@login_required
def dashboard_candidat(request):
    """Tableau de bord du candidat"""
    try:
        candidat = request.user.candidat
    except Candidat.DoesNotExist:
        return redirect('recrutement:inscription')

    if not (candidat.date_naissance and candidat.adresse and candidat.cv and candidat.lettre_motivation):
        # CRITICAL: toujours utiliser le namespace recrutement
        # (en production, un ancien reverse('profil') sans namespace a déjÃ  causé NoReverseMatch)
        return redirect('recrutement:profil')

    # Vérifier si le candidat a déjÃ  une session de test
    session_existante = SessionTest.objects.filter(candidat=candidat).first()

    return render(request, 'recrutement/dashboard.html', {
        'candidat': candidat,
        # Le template attend `session_test`
        'session_test': session_existante
    })


@login_required
def demarrer_test(request):
    """Démarre une nouvelle session de test"""
    try:
        candidat = request.user.candidat
    except Candidat.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Vous devez d\'abord vous inscrire'
        })

    # Vérifier si le candidat a déjÃ  passé le test
    session_existante = SessionTest.objects.filter(
        candidat=candidat,
        statut__in=['termine', 'expire']
    ).first()

    if session_existante:
        return JsonResponse({
            'success': False,
            'error': 'Vous avez déjÃ  passé le test. Vous ne pouvez pas le refaire.'
        })

    # Vérifier si une session est déjÃ  en cours
    session_en_cours = SessionTest.objects.filter(
        candidat=candidat,
        statut='en_cours'
    ).first()

    if session_en_cours:
        # Vérifier si elle est expirée
        if session_en_cours.est_expire():
            session_en_cours.statut = 'expire'
            session_en_cours.save()
            return JsonResponse({
                'success': False,
                'error': 'Votre session précédente a expiré. Vous ne pouvez pas recommencer.'
            })
        else:
            # Rediriger vers la session en cours
            return JsonResponse({
                'success': True,
                'redirect_url': f'/recrutement/test/{session_en_cours.id}/'
            })

    with transaction.atomic():
        try:
            session = _creer_session_test(candidat)
        except ValueError as exc:
            return JsonResponse({
                'success': False,
                'error': str(exc)
            })

    return JsonResponse({
        'success': True,
        'redirect_url': f'/recrutement/test/{session.id}/'
    })


@login_required
def page_test(request, session_id):
    """Page du test avec les questions"""
    session = _get_candidate_session_for_user(request.user, session_id)
    if not session:
        _log_missing_candidate_session(request, session_id, 'page_test')
        messages.error(request, "Cette session de test n'existe plus ou n'est plus accessible.")
        return redirect('recrutement:dashboard')

    # Une session terminée envoie vers la page de résultats.
    if session.statut == 'termine':
        return redirect('recrutement:resultats', session_id=session.id)

    # Une session expirée reste affichée pour permettre le dépot final.
    if session.statut == 'en_cours' and session.est_expire():
        session.statut = 'expire'
        session.save(update_fields=['statut', 'updated_at'])

    # Récupérer les questions avec les réponses
    reponses = session.reponses.select_related('question').order_by('question__ordre')
    # Préparer les options QCM coté Python (templates Django ne supportent pas .split)
    for reponse in reponses:
        options = reponse.question.options_qcm or ''
        reponse.options_list = [opt.strip() for opt in options.split('|') if opt.strip()]

    return render(request, 'recrutement/test.html', {
        'session': session,
        'reponses': reponses,
        'temps_restant': session.temps_restant_secondes(),
        'test_expire': session.statut == 'expire',
    })


@login_required
@require_http_methods(["POST"])
def enregistrer_reponse(request, session_id):
    """Enregistre la réponse d'une question"""
    try:
        session = _get_candidate_session_for_user(request.user, session_id)
        if not session:
            _log_missing_candidate_session(request, session_id, 'enregistrer_reponse')
            return JsonResponse({
                'success': False,
                'error': "Cette session de test n'existe plus ou n'est plus accessible.",
                'session_missing': True,
                'redirect_url': '/recrutement/dashboard/',
            }, status=404)

        # Vérifier si la session est toujours valide
        if session.statut != 'en_cours':
            return JsonResponse({
                'success': False,
                'error': 'La session n\'est plus active'
            })

        if session.est_expire():
            session.statut = 'expire'
            session.save()
            return JsonResponse({
                'success': False,
                'error': 'Le temps est écoulé',
                'expired': True
            })

        data = json.loads(request.body)
        reponse_id = data.get('reponse_id')
        question_id = data.get('question_id')
        reponse_donnee = data.get('reponse')

        # Enregistrer la réponse
        if reponse_id:
            reponse = ReponseCandidat.objects.get(
                id=reponse_id,
                session=session
            )
        else:
            reponse = ReponseCandidat.objects.get(
                session=session,
                question_id=question_id
            )
        reponse.reponse_donnee = reponse_donnee
        reponse.save()

        return JsonResponse({
            'success': True,
            'temps_restant': session.temps_restant_secondes()
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@require_http_methods(["POST"])
def soumettre_test(request, session_id):
    """Soumet le test et calcule le score"""
    try:
        session = _get_candidate_session_for_user(request.user, session_id)
        if not session:
            _log_missing_candidate_session(request, session_id, 'soumettre_test')
            return JsonResponse({
                'success': False,
                'error': "Cette session de test n'existe plus ou n'est plus accessible.",
                'session_missing': True,
                'redirect_url': '/recrutement/dashboard/',
            }, status=404)

        if session.statut == 'termine':
            return JsonResponse({
                'success': False,
                'error': 'Le test a déjÃ  été soumis'
            })

        if session.statut == 'en_cours' and session.est_expire():
            session.statut = 'expire'
            session.save(update_fields=['statut', 'updated_at'])

        if session.statut not in ['en_cours', 'expire']:
            return JsonResponse({
                'success': False,
                'error': 'La session n\'est plus disponible pour soumission'
            })

        # Ã‰valuer toutes les réponses
        for reponse in session.reponses.all():
            reponse.evaluer()

        session.date_fin = timezone.now()
        session.statut = 'termine'
        session.save(update_fields=['date_fin', 'statut', 'updated_at'])
        session.calculer_score()
        session.candidat.statut = 'test_termine'
        session.candidat.save(update_fields=['statut'])

        preconfig = CandidatPreconfigure.objects.filter(candidat=session.candidat).first()
        if not preconfig:
            preconfig = CandidatPreconfigure.objects.filter(email__iexact=session.candidat.email).first()
        if preconfig:
            preconfig.candidat = session.candidat
            preconfig.test_complete = True
            if preconfig.screening_statut != 'elimine':
                preconfig.screening_statut = 'test_complete'
            preconfig.invite_test_envoyee = True
            preconfig.save(update_fields=['candidat', 'test_complete', 'screening_statut', 'invite_test_envoyee'])

        return JsonResponse({
            'success': True,
            'redirect_url': f'/recrutement/resultats/{session.id}/'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def resultats_test(request, session_id):
    """Page des résultats du test"""
    session = _get_candidate_session_for_user(request.user, session_id)
    if not session:
        _log_missing_candidate_session(request, session_id, 'resultats_test')
        messages.error(request, "Cette session de test n'existe plus ou n'est plus accessible.")
        return redirect('recrutement:dashboard')

    if session.statut not in ['termine', 'expire']:
        return redirect('recrutement:test', session_id=session.id)

    # Récupérer les réponses avec les questions
    reponses = session.reponses.select_related('question').order_by('question__ordre')

    return render(request, 'recrutement/resultats.html', {
        'session': session,
        'reponses': reponses
    })


# ADMIN - Gestion des questions

@login_required
def gestion_questions(request):
    """Page de gestion des questions par poste (admin)"""
    if not request.user.is_staff:
        return redirect('dashboard')

    postes = Poste.objects.all()
    questions = QuestionTest.objects.select_related('poste').order_by('poste', 'ordre')

    return render(request, 'recrutement/gestion_questions.html', {
        'postes': postes,
        'questions': questions
    })


@login_required
@require_http_methods(["POST"])
def creer_question(request):
    """Crée une nouvelle question"""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'})

    try:
        data = json.loads(request.body)

        question = QuestionTest.objects.create(
            poste_id=data.get('poste_id'),
            type_question=data.get('type_question'),
            texte_question=data.get('texte_question'),
            options_qcm=data.get('options_qcm', ''),
            reponse_correcte=data.get('reponse_correcte'),
            points=data.get('points', 1),
            ordre=data.get('ordre', 0)
        )

        return JsonResponse({
            'success': True,
            'message': 'Question créée avec succès',
            'question_id': str(question.id)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
