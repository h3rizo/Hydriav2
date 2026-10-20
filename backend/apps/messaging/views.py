from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Conversation, Message, Participant, Call
from .repair_sync import try_complete_repair_from_message, ensure_repair_conversation
from .forfaitaire_sync import sync_forfaitaire_conversations_for_employee
from apps.employees.models import Employe
import json
import os


def _sync_repair_conversations_for_employee(employe):
    """
    Assure que les conversations de suivi réparation existent avant affichage
    de la liste des conversations.
    """
    try:
        from apps.planning.models import Planning, ActivitePoste
        from apps.planning.views_reparations import get_repair_activities

        repair_activities = get_repair_activities()
        fiche_poste_ids = list(
            ActivitePoste.objects.filter(
                activite__in=repair_activities,
                fiche_poste__isnull=False
            ).values_list('fiche_poste_id', flat=True).distinct()
        )
        if not fiche_poste_ids:
            return

        repairs_qs = Planning.objects.filter(
            fiche_poste_id__in=fiche_poste_ids,
            estvalide=False,
        ).select_related(
            'employe',
            'employe__base',
            'employe__base__organisation',
            'ouvrage',
        )

        if employe and employe.base_id and employe.base and employe.base.organisation_id:
            repairs_qs = repairs_qs.filter(employe__base__organisation=employe.base.organisation)

        for planning in repairs_qs.order_by('-date')[:400]:
            ensure_repair_conversation(planning, actor=None, notify=False)
    except Exception:
        # Ne jamais bloquer la messagerie si la sync réparation échoue
        pass


def _sync_forfaitaire_conversations_for_employee(employe):
    """Assure la synchro des conversations de paiements forfaitaires."""
    try:
        sync_forfaitaire_conversations_for_employee(employe=employe, limit=1000)
    except Exception:
        pass


def conversations_list(request):
    """Liste des conversations de l'utilisateur connecté"""
    # Récupérer l'employé de l'utilisateur connecté
    try:
        employe = request.user.employe
    except AttributeError:
        # Si l'utilisateur n'a pas d'employé lié, afficher message d'erreur
        employe = None
        participations = Participant.objects.none()
        return render(request, 'messaging/conversations_list.html', {
            'conversations': [],
            'stats': {'total': 0, 'directs': 0, 'groupes': 0, 'non_lus': 0},
            'employes': [],
            'employe_actuel': None,
        })

    # Filtres
    search = request.GET.get('search', '')
    type_filter = request.GET.get('type', 'all')

    _sync_repair_conversations_for_employee(employe)
    _sync_forfaitaire_conversations_for_employee(employe)

    # Conversations de l'employé
    participations = Participant.objects.filter(employe=employe)
    conversation_ids = participations.values_list('conversation_id', flat=True)

    conversations = Conversation.objects.filter(
        id__in=conversation_ids,
        archivee=False
    ).select_related('createur').prefetch_related('participants__employe')

    # Filtres
    if search:
        conversations = conversations.filter(
            Q(nom_groupe__icontains=search) |
            Q(participants__employe__nom_employe__icontains=search)
        ).distinct()

    if type_filter != 'all':
        conversations = conversations.filter(type=type_filter)

    # Pas d'annotation pour l'instant (nécessiterait une sous-requête complexe)
    # Les messages non lus seront calculés via la propriété du modèle Participant

    # Statistiques
    stats = {
        'total': participations.count(),
        'directs': participations.filter(conversation__type='direct').count(),
        'groupes': participations.filter(conversation__type='group').count(),
        'non_lus': sum([p.messages_non_lus for p in participations]),
    }

    # Employés disponibles pour démarrer une conversation (avec base et organisation)
    employes = Employe.objects.filter(
        date_debauchage__isnull=True
    ).exclude(
        id=employe.id
    ).select_related(
        'base__organisation'  # Organisation accessible via base
    ).order_by('surnom')

    context = {
        'conversations': conversations,
        'stats': stats,
        'search': search,
        'type_filter': type_filter,
        'employes': employes,
        'employe_actuel': employe,
    }

    return render(request, 'messaging/conversations_list.html', context)

def conversation_detail(request, conversation_id):
    """Page de chat d'une conversation"""
    conversation = get_object_or_404(Conversation, id=conversation_id)

    # Récupérer l'employé de l'utilisateur connecté
    try:
        employe = request.user.employe
    except AttributeError:
        # Si l'utilisateur n'a pas d'employé lié, rediriger
        return redirect('messaging:conversations_list')

    # Vérifier que l'employé est participant
    participant = Participant.objects.filter(
        conversation=conversation,
        employe=employe
    ).first()

    if not participant:
        return redirect('messaging:conversations_list')

    # Messages de la conversation
    # Protection perf: ne charger que les derniers messages pour éviter
    # les pages qui deviennent trop lourdes sur des conversations volumineuses.
    initial_limit = 250
    messages = list(
        conversation.messages.filter(supprime=False)
        .select_related('expediteur', 'message_repondu')
        .order_by('-date_envoi')[:initial_limit]
    )
    messages.reverse()

    # Marquer comme lu
    participant.date_derniere_lecture = timezone.now()
    participant.save()

    # Participants de la conversation
    participants = conversation.participants.select_related('employe').all()

    # Appels récents
    appels = conversation.appels.select_related('initiateur')[:10]

    context = {
        'conversation': conversation,
        'conversation_messages': messages,
        'participants': participants,
        'appels': appels,
        'employe_actuel': employe,
        'participant': participant,
    }

    return render(request, 'messaging/conversation_detail.html', context)

@csrf_exempt
def conversation_create(request):
    """Créer une nouvelle conversation"""
    if request.method == 'POST':
        data = json.loads(request.body)

        # Récupérer l'employé de l'utilisateur connecté
        try:
            employe = request.user.employe
        except AttributeError:
            return JsonResponse({'error': 'Utilisateur non lié à un employé'}, status=403)

        type_conv = data.get('type', 'direct')

        # Créer la conversation
        conversation = Conversation.objects.create(
            type=type_conv,
            nom_groupe=data.get('nom_groupe') if type_conv == 'group' else None,
            description=data.get('description'),
            createur=employe
        )

        # Ajouter le créateur comme participant admin
        Participant.objects.create(
            conversation=conversation,
            employe=employe,
            est_admin=True
        )

        # Ajouter les autres participants
        employe_ids = data.get('employes', [])
        for emp_id in employe_ids:
            emp = Employe.objects.get(id=emp_id)
            Participant.objects.create(
                conversation=conversation,
                employe=emp,
                est_admin=False
            )

        # Message système de création
        if type_conv == 'group':
            Message.objects.create(
                conversation=conversation,
                type='system',
                contenu=f"{employe.nom_employe} a créé le groupe {conversation.nom_groupe}"
            )

        return JsonResponse({'id': conversation.id, 'success': True})

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@csrf_exempt
def message_send(request, conversation_id):
    """Envoyer un message"""
    if request.method == 'POST':
        conversation = get_object_or_404(Conversation, id=conversation_id)

        # Récupérer l'employé de l'utilisateur connecté
        try:
            employe = request.user.employe
        except AttributeError:
            return JsonResponse({'error': 'Utilisateur non lié à un employé'}, status=403)

        if request.content_type == 'application/json':
            data = json.loads(request.body)
            contenu = data.get('contenu', '')
            type_msg = data.get('type', 'text')
            message_repondu_id = data.get('message_repondu_id')
        else:
            contenu = request.POST.get('contenu', '')
            type_msg = request.POST.get('type', 'text')
            message_repondu_id = request.POST.get('message_repondu_id')

        if not contenu and 'fichier' in request.FILES:
            contenu = request.FILES['fichier'].name

        message = Message.objects.create(
            conversation=conversation,
            expediteur=employe,
            type=type_msg,
            contenu=contenu,
            message_repondu_id=message_repondu_id if message_repondu_id else None
        )

        # Gérer le fichier si présent
        if 'fichier' in request.FILES:
            message.fichier = request.FILES['fichier']
            message.save()

        # Mettre à jour la dernière activité de la conversation
        conversation.derniere_activite = timezone.now()
        conversation.save()

        repair_action = {'matched': False, 'completed': False}
        if type_msg == 'text':
            repair_action = try_complete_repair_from_message(
                conversation=conversation,
                sender=employe,
                text=contenu,
            )

        file_url = message.fichier.url if message.fichier else None
        file_name = os.path.basename(message.fichier.name) if message.fichier else None
        return JsonResponse({
            'id': message.id,
            'success': True,
            'date_envoi': message.date_envoi.isoformat(),
            'expediteur': message.expediteur.nom_employe,
            'file_url': file_url,
            'file_name': file_name,
            'repair_completed': bool(repair_action.get('completed')),
            'repair_planning_id': repair_action.get('planning_id'),
        })

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@csrf_exempt
def message_delete(request, message_id):
    """Supprimer un message"""
    if request.method == 'POST':
        message = get_object_or_404(Message, id=message_id)

        # Récupérer l'employé de l'utilisateur connecté
        try:
            employe = request.user.employe
        except AttributeError:
            return JsonResponse({'error': 'Utilisateur non lié à un employé'}, status=403)

        # Vérifier que c'est l'expéditeur
        if message.expediteur == employe:
            message.supprime = True
            message.save()
            return JsonResponse({'success': True})

        return JsonResponse({'error': 'Non autorisé'}, status=403)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@csrf_exempt
def call_start(request, conversation_id):
    """Démarrer un appel"""
    if request.method == 'POST':
        data = json.loads(request.body)
        conversation = get_object_or_404(Conversation, id=conversation_id)

        # Récupérer l'employé de l'utilisateur connecté
        try:
            employe = request.user.employe
        except AttributeError:
            return JsonResponse({'error': 'Utilisateur non lié à un employé'}, status=403)

        call = Call.objects.create(
            conversation=conversation,
            initiateur=employe,
            type=data.get('type', 'audio'),
            statut='en_cours'
        )

        # Message système
        Message.objects.create(
            conversation=conversation,
            type='system',
            contenu=f"{employe.nom_employe} a démarré un appel {call.get_type_display()}"
        )

        return JsonResponse({
            'id': call.id,
            'success': True
        })

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@csrf_exempt
def call_end(request, call_id):
    """Terminer un appel"""
    if request.method == 'POST':
        call = get_object_or_404(Call, id=call_id)
        call.date_fin = timezone.now()
        call.statut = 'termine'
        call.duree_secondes = int((call.date_fin - call.date_debut).total_seconds())
        call.save()

        return JsonResponse({
            'success': True,
            'duree': call.duree_formatee
        })

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

def messages_api(request, conversation_id):
    """API pour récupérer les nouveaux messages (polling)"""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    since = request.GET.get('since')

    messages = conversation.messages.filter(supprime=False)

    if since:
        since_dt = parse_datetime(since)
        if since_dt is not None:
            if timezone.is_naive(since_dt):
                since_dt = timezone.make_aware(since_dt, timezone.get_current_timezone())
            messages = messages.filter(date_envoi__gt=since_dt)
        else:
            # since invalide: fallback sur une fenetre courte au lieu de
            # renvoyer tout l'historique.
            messages = messages.order_by('-date_envoi')[:200]
            messages = sorted(messages, key=lambda m: m.date_envoi)
            data = [{
                'id': m.id,
                'expediteur': m.expediteur.nom_employe if m.expediteur else 'Système',
                'expediteur_id': m.expediteur.id if m.expediteur else None,
                'contenu': m.contenu,
                'type': m.type,
                'date_envoi': m.date_envoi.isoformat(),
                'file_url': m.fichier.url if m.fichier else None,
                'file_name': os.path.basename(m.fichier.name) if m.fichier else None,
            } for m in messages]
            return JsonResponse({'messages': data})
    else:
        # Pas de filtre since: limiter pour proteger l'endpoint.
        messages = messages.order_by('-date_envoi')[:200]
        messages = sorted(messages, key=lambda m: m.date_envoi)
        data = [{
            'id': m.id,
            'expediteur': m.expediteur.nom_employe if m.expediteur else 'Système',
            'expediteur_id': m.expediteur.id if m.expediteur else None,
            'contenu': m.contenu,
            'type': m.type,
            'date_envoi': m.date_envoi.isoformat(),
            'file_url': m.fichier.url if m.fichier else None,
            'file_name': os.path.basename(m.fichier.name) if m.fichier else None,
        } for m in messages]
        return JsonResponse({'messages': data})

    messages = messages.select_related('expediteur').order_by('date_envoi')

    data = [{
        'id': m.id,
        'expediteur': m.expediteur.nom_employe if m.expediteur else 'Système',
        'expediteur_id': m.expediteur.id if m.expediteur else None,
        'contenu': m.contenu,
        'type': m.type,
        'date_envoi': m.date_envoi.isoformat(),
        'file_url': m.fichier.url if m.fichier else None,
        'file_name': os.path.basename(m.fichier.name) if m.fichier else None,
    } for m in messages]

    return JsonResponse({'messages': data})


def unread_count_api(request):
    """API: total des messages non lus de l'employe connecte."""
    if not request.user.is_authenticated:
        return JsonResponse({'unread_count': 0})

    try:
        employe = request.user.employe
    except Exception:
        return JsonResponse({'unread_count': 0})

    participations = Participant.objects.filter(
        employe=employe
    ).select_related('conversation')

    total = sum(p.messages_non_lus for p in participations)
    return JsonResponse({'unread_count': total})


# ============================================================
# Rappel mensuel factures non pointees - formulaire de commentaires
# ============================================================

@login_required
def commentaire_relance(request, annee, mois, employe_id):
    """
    Page consolidee permettant a un responsable d'ouvrage de consulter les
    points d'eau concernes par un rappel mensuel de factures non pointees et
    d'ajouter des commentaires (journal append-only, jamais d'edition en
    place, jamais d'effet sur le pointage des factures).

    Acces reserve au responsable concerne lui-meme, ou a un admin/directeur
    (has_admin_access) pour du support.
    """
    from django.http import Http404, HttpResponseForbidden
    from django.contrib import messages

    from apps.employees.permissions import has_admin_access

    from .forms import CommentaireRelanceFormSet
    from .models import CommentaireRelance, RelanceFacturesNonPointees
    from .monthly_billing_reminder import calculer_periode_cible, construire_regroupement

    employe_cible = get_object_or_404(Employe, id=employe_id)
    employe_connecte = getattr(request.user, 'employe', None)

    est_admin = request.user.is_superuser or has_admin_access(request.user)
    if not est_admin:
        if employe_connecte is None or employe_connecte.id != employe_cible.id:
            return HttpResponseForbidden("Vous n'avez pas accès à cette page.")

    annee, mois, date_fin_periode = calculer_periode_cible(annee, mois)
    regroupement = construire_regroupement(annee, mois)
    entree = regroupement.get(employe_cible.id)
    if entree is None:
        raise Http404("Aucune facture non pointée pour ce responsable sur cette période.")

    # Ensemble des points d'eau reellement inclus dans le regroupement -
    # seule source de verite pour valider les soumissions (jamais confiance
    # au POST du client).
    points_eau_valides = set()
    for ouvrage_entree in entree['ouvrages'].values():
        for pe_entree in ouvrage_entree['points_eau'].values():
            points_eau_valides.add(str(pe_entree['point_eau'].id))

    relance, _ = RelanceFacturesNonPointees.objects.get_or_create(
        employe=employe_cible, annee=annee, mois=mois, est_test=False,
        defaults={'statut': 'envoye'},
    )

    commentaires_existants = CommentaireRelance.objects.filter(
        relance=relance, entity_type='point_eau',
    ).select_related('employe_auteur').order_by('created_at')
    commentaires_par_point_eau = {}
    for commentaire in commentaires_existants:
        commentaires_par_point_eau.setdefault(commentaire.entity_id, []).append(commentaire)

    if request.method == 'POST':
        formset = CommentaireRelanceFormSet(request.POST, prefix='commentaires')
        if formset.is_valid():
            premiere_soumission_reussie = False
            for form in formset:
                contenu = (form.cleaned_data.get('contenu') or '').strip()
                point_eau_id = (form.cleaned_data.get('point_eau_id') or '').strip()
                if not contenu or not point_eau_id:
                    continue  # ligne vide du formset, ignoree

                if point_eau_id not in points_eau_valides:
                    return HttpResponseForbidden("Point d'eau non autorisé pour cette relance.")

                CommentaireRelance.objects.create(
                    relance=relance,
                    employe_auteur=employe_cible,
                    entity_type='point_eau',
                    entity_id=point_eau_id,
                    contenu=contenu,
                )
                premiere_soumission_reussie = True

            if premiere_soumission_reussie:
                if relance.date_premiere_reponse is None:
                    relance.date_premiere_reponse = timezone.now()
                    relance.save(update_fields=['date_premiere_reponse'])
                messages.success(request, "Commentaire(s) enregistré(s).")
            else:
                messages.info(request, "Aucun commentaire saisi.")
            return redirect(request.path)
    else:
        initial = [
            {'point_eau_id': pe_id}
            for pe_id in sorted(points_eau_valides)
        ]
        formset = CommentaireRelanceFormSet(prefix='commentaires', initial=initial)

    # Transformation du regroupement en listes triees pour l'affichage,
    # avec compteurs par point d'eau (meme logique que le mailer).
    ouvrages_affichage = []
    nb_points_eau = 0
    nb_factures = 0
    for ouvrage_entree in sorted(entree['ouvrages'].values(), key=lambda o: o['ouvrage'].nom_ouvrage):
        points_eau_affichage = []
        for pe_entree in sorted(ouvrage_entree['points_eau'].values(), key=lambda p: p['point_eau'].nomabonne or ''):
            lignes = sorted(pe_entree['lignes'], key=lambda l: l['date'])
            point_eau_id_str = str(pe_entree['point_eau'].id)
            points_eau_affichage.append({
                'point_eau': pe_entree['point_eau'],
                'lignes': lignes,
                'nb_factures': len(lignes),
                'commentaires': commentaires_par_point_eau.get(point_eau_id_str, []),
            })
            nb_points_eau += 1
            nb_factures += len(lignes)
        ouvrages_affichage.append({
            'ouvrage': ouvrage_entree['ouvrage'],
            'points_eau': points_eau_affichage,
        })

    return render(request, 'messaging/commentaire_relance.html', {
        'employe': employe_cible,
        'annee': annee,
        'mois': mois,
        'date_fin_periode': date_fin_periode,
        'ouvrages': ouvrages_affichage,
        'nb_points_eau': nb_points_eau,
        'nb_factures': nb_factures,
        'formset': formset,
        'relance': relance,
        'est_admin_consultant': est_admin and (employe_connecte is None or employe_connecte.id != employe_cible.id),
    })
