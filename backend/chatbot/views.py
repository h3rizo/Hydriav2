from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

import json
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, Any

from .models import ChatSession, ChatMessage, Conversation, ConversationParticipant, ConversationMessage, MessageReaction
from .services.ai_assistant import AIAssistant
from .services.file_exporter import FileExporter

# Import pour le compteur de visites
try:
    from apps.core.middleware import VISIT_COUNTS
except ImportError:
    VISIT_COUNTS = {}

User = get_user_model()


@login_required
def chat_interface(request):
    """
    Interface principale du chatbot
    """
    # Récupérer les sessions récentes de l'utilisateur
    recent_sessions = ChatSession.objects.filter(
        user=request.user
    ).order_by('-updated_at')[:10]
    
    context = {
        'recent_sessions': recent_sessions,
        'user': request.user,
    }
    
    return render(request, 'chatbot/chat_interface.html', context)


@login_required
def chat_menu(request):
    """
    Menu principal du chat (IA + Conversations)
    """
    # Récupérer les sessions IA récentes
    recent_ai_sessions = ChatSession.objects.filter(
        user=request.user
    ).order_by('-updated_at')[:5]
    
    # Récupérer les conversations récentes
    recent_conversations = Conversation.objects.filter(
        participants=request.user,
        is_active=True
    ).order_by('-updated_at')[:5]
    
    context = {
        'recent_ai_sessions': recent_ai_sessions,
        'recent_conversations': recent_conversations,
        'user': request.user,
    }
    
    return render(request, 'chatbot/chat_menu.html', context)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def send_message(request):
    """
    Envoie un message et génère la réponse de l'IA
    """
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        
        if not message:
            return JsonResponse({
                'success': False,
                'error': 'Message vide'
            })
        
        # Récupérer ou créer la session
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Session introuvable'
                })
        else:
            # Créer une nouvelle session
            session = ChatSession.objects.create(
                user=request.user,
                title=message[:50] + ('...' if len(message) > 50 else ''),
                started_at=timezone.now()
            )
        
        # Enregistrer le message utilisateur
        user_message = ChatMessage.objects.create(
            session=session,
            role='user',
            content=message,
            created_at=timezone.now()
        )
        
        # Préparer le contexte de session
        session_context = {
            'user_id': request.user.id,
            'session_id': session.id,
            'recent_messages': list(session.messages.order_by('-created_at')[:10].values(
                'role', 'content', 'created_at'
            ))
        }
        
        # Traiter avec l'assistant IA
        ai_assistant = AIAssistant()
        
        # Exécuter de manière asynchrone
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ai_response = loop.run_until_complete(
                ai_assistant.process_message(message, session_context)
            )
        finally:
            loop.close()
        
        # Enregistrer la réponse de l'IA
        assistant_message = ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=ai_response.get('response', 'Désolé, je n\'ai pas pu traiter votre demande.'),
            metadata=ai_response.get('metadata', {}),
            created_at=timezone.now()
        )
        
        # Mettre à jour la session
        session.updated_at = timezone.now()
        session.save()
        
        return JsonResponse({
            'success': True,
            'response': {
                'id': assistant_message.id,
                'content': assistant_message.content,
                'metadata': assistant_message.metadata,
                'timestamp': assistant_message.created_at.isoformat()
            },
            'session': {
                'id': session.id,
                'title': session.title,
                'updated_at': session.updated_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


# =============================================================================
# VUE POUR LE COMPTEUR DE VISITES DE PAGE (POUR TEST)
# =============================================================================

@login_required
def page_visits_report(request):
    """
    Affiche un rapport des pages visitées pendant la session de test.
    """
    # On récupère toutes les URLs non-API et non-admin du projet
    from django.urls import get_resolver
    
    all_urls = set()
    
    def get_urls(resolver):
        for pattern in resolver.url_patterns:
            if hasattr(pattern, 'url_patterns'): # Cas des include()
                get_urls(pattern)
            else:
                path = f"/{pattern.pattern}"
                if (not path.startswith('/api/') and not path.startswith('/admin/') and 
                    '<' not in path and '{' not in path): # Exclure les URLs avec paramètres
                    all_urls.add(path.replace('^', '').replace('$', ''))

    get_urls(get_resolver())

    visited_pages = {path: count for path, count in VISIT_COUNTS.items()}
    not_visited_pages = sorted(list(all_urls - set(visited_pages.keys())))

    return render(request, 'chatbot/page_visits_report.html', {
        'visited_pages': sorted(visited_pages.items(), key=lambda item: item[1], reverse=True),
        'not_visited_pages': not_visited_pages,
        'total_visited': len(visited_pages),
        'total_not_visited': len(not_visited_pages),
    })


@require_http_methods(["GET"])
@login_required
def list_sessions(request):
    """
    Liste les sessions de chat de l'utilisateur
    """
    try:
        page = int(request.GET.get('page', 1))
        search = request.GET.get('search', '').strip()
        
        sessions = ChatSession.objects.filter(user=request.user)
        
        if search:
            sessions = sessions.filter(
                Q(title__icontains=search) |
                Q(messages__content__icontains=search)
            ).distinct()
        
        sessions = sessions.order_by('-updated_at')
        
        paginator = Paginator(sessions, 20)
        page_obj = paginator.get_page(page)
        
        sessions_data = []
        for session in page_obj:
            last_message = session.messages.order_by('-created_at').first()
            sessions_data.append({
                'id': session.id,
                'title': session.title,
                'started_at': session.started_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.messages.count(),
                'last_message': {
                    'content': last_message.content[:100] + ('...' if len(last_message.content) > 100 else '') if last_message else None,
                    'timestamp': last_message.created_at.isoformat() if last_message else None
                }
            })
        
        return JsonResponse({
            'success': True,
            'sessions': sessions_data,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
                'total_count': paginator.count
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@require_http_methods(["GET"])
@login_required
def get_session(request, session_id):
    """
    Récupère les détails d'une session spécifique
    """
    try:
        session = get_object_or_404(ChatSession, id=session_id, user=request.user)
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': session.id,
                'title': session.title,
                'started_at': session.started_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.messages.count()
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@require_http_methods(["GET"])
@login_required
def get_messages(request, session_id):
    """
    Récupère les messages d'une session
    """
    try:
        session = get_object_or_404(ChatSession, id=session_id, user=request.user)
        
        page = int(request.GET.get('page', 1))
        messages = session.messages.order_by('created_at')
        
        paginator = Paginator(messages, 50)
        page_obj = paginator.get_page(page)
        
        messages_data = []
        for message in page_obj:
            messages_data.append({
                'id': message.id,
                'role': message.role,
                'content': message.content,
                'metadata': message.metadata,
                'timestamp': message.created_at.isoformat()
            })
        
        return JsonResponse({
            'success': True,
            'messages': messages_data,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
                'total_count': paginator.count
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def create_session(request):
    """
    Crée une nouvelle session de chat
    """
    try:
        data = json.loads(request.body)
        title = data.get('title', f'Nouvelle conversation - {timezone.now().strftime("%d/%m %H:%M")}')
        
        session = ChatSession.objects.create(
            user=request.user,
            title=title[:200],  # Limiter la longueur du titre
            started_at=timezone.now()
        )
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': session.id,
                'title': session.title,
                'started_at': session.started_at.isoformat(),
                'updated_at': session.updated_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@require_http_methods(["DELETE"])
@login_required
def delete_session(request, session_id):
    """
    Supprime une session de chat
    """
    try:
        session = get_object_or_404(ChatSession, id=session_id, user=request.user)
        session.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Session supprimée avec succès'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@require_http_methods(["GET"])
@login_required
def export_session_pdf(request, session_id):
    """
    Exporte une session en PDF
    """
    try:
        session = get_object_or_404(ChatSession, id=session_id, user=request.user)
        messages = session.messages.order_by('created_at')
        
        # Préparer les données pour le PDF
        report_data = {
            'title': f'Conversation - {session.title}',
            'summary': f'Conversation démarrée le {session.started_at.strftime("%d/%m/%Y à %H:%M")}',
            'conversation_data': {
                'session_title': session.title,
                'started_at': session.started_at,
                'messages': list(messages.values('role', 'content', 'created_at'))
            },
            'metrics': [{
                'label': 'Nombre de messages',
                'value': messages.count()
            }, {
                'label': 'Durée de la conversation',
                'value': f'{(session.updated_at - session.started_at).days} jour(s)' if session.updated_at else 'En cours'
            }]
        }
        
        # Générer le PDF
        exporter = FileExporter()
        pdf_path = exporter.create_pdf_report(report_data, f'conversation_{session_id}.pdf')
        
        # Retourner le fichier
        with open(pdf_path, 'rb') as pdf_file:
            response = HttpResponse(pdf_file.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="conversation_{session.title[:20]}.pdf"'
            return response
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la génération du PDF: {str(e)}'
        })


@require_http_methods(["GET"])
@login_required
def export_session_excel(request, session_id):
    """
    Exporte une session en Excel
    """
    try:
        session = get_object_or_404(ChatSession, id=session_id, user=request.user)
        messages = session.messages.order_by('created_at')
        
        # Préparer les données pour Excel
        excel_data = {
            'title': f'Conversation - {session.title}',
            'sheets': {
                'Messages': [
                    ['Rôle', 'Contenu', 'Horodatage']
                ] + [[msg.role, msg.content, msg.timestamp.strftime('%d/%m/%Y %H:%M:%S')] for msg in messages]
            }
        }
        
        # Générer le fichier Excel
        exporter = FileExporter()
        excel_path = exporter.create_excel_report(excel_data, f'conversation_{session_id}.xlsx')
        
        # Retourner le fichier
        with open(excel_path, 'rb') as excel_file:
            response = HttpResponse(
                excel_file.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="conversation_{session.title[:20]}.xlsx"'
            return response
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la génération du fichier Excel: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def generate_report(request):
    """
    Génère un rapport personnalisé
    """
    try:
        data = json.loads(request.body)
        report_type = data.get('type', 'pdf')
        report_title = data.get('title', 'Rapport Hydria')
        include_data = data.get('include_data', [])
        
        # Préparer les données du rapport
        report_data = {
            'title': report_title,
            'summary': f'Rapport généré le {timezone.now().strftime("%d/%m/%Y à %H:%M")}',
            'metrics': [],
            'table_data': {},
            'charts': []
        }
        
        # Ajouter des métriques selon les données demandées
        if 'sessions' in include_data:
            user_sessions = ChatSession.objects.filter(user=request.user)
            report_data['metrics'].append({
                'label': 'Total des conversations',
                'value': user_sessions.count()
            })
            
            recent_sessions = user_sessions.filter(
                started_at__gte=timezone.now() - timedelta(days=30)
            )
            report_data['metrics'].append({
                'label': 'Conversations ce mois-ci',
                'value': recent_sessions.count()
            })
        
        if 'messages' in include_data:
            user_messages = ChatMessage.objects.filter(session__user=request.user)
            report_data['metrics'].append({
                'label': 'Total des messages',
                'value': user_messages.count()
            })
        
        # Générer le rapport
        exporter = FileExporter()
        
        if report_type == 'excel':
            file_path = exporter.create_excel_report(report_data, 'rapport_hydria.xlsx')
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = 'rapport_hydria.xlsx'
        else:
            file_path = exporter.create_pdf_report(report_data, 'rapport_hydria.pdf')
            content_type = 'application/pdf'
            filename = 'rapport_hydria.pdf'
        
        # Retourner l'URL de téléchargement
        return JsonResponse({
            'success': True,
            'download_url': reverse('chatbot:download_report', kwargs={'filename': os.path.basename(file_path)}),
            'filename': filename
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la génération du rapport: {str(e)}'
        })


@require_http_methods(["GET"])
@login_required
def search_sessions(request):
    """
    Recherche dans les sessions et messages
    """
    try:
        query = request.GET.get('q', '').strip()
        session_filter = request.GET.get('filter', 'all')  # all, recent, old
        page = int(request.GET.get('page', 1))
        
        if not query:
            return JsonResponse({
                'success': False,
                'error': 'Requête de recherche vide'
            })
        
        # Base queryset
        sessions = ChatSession.objects.filter(user=request.user)
        
        # Appliquer les filtres de date
        if session_filter == 'recent':
            sessions = sessions.filter(started_at__gte=timezone.now() - timedelta(days=7))
        elif session_filter == 'old':
            sessions = sessions.filter(started_at__lt=timezone.now() - timedelta(days=30))
        
        # Recherche dans les titres et messages
        sessions = sessions.filter(
            Q(title__icontains=query) |
            Q(messages__content__icontains=query)
        ).distinct().order_by('-updated_at')
        
        # Pagination
        paginator = Paginator(sessions, 20)
        page_obj = paginator.get_page(page)
        
        results = []
        for session in page_obj:
            # Trouver les messages qui correspondent
            matching_messages = session.messages.filter(
                content__icontains=query
            ).order_by('created_at')[:3]
            
            results.append({
                'id': session.id,
                'title': session.title,
                'started_at': session.started_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'matching_messages': [
                    {
                        'role': msg.role,
                        'content': msg.content[:200] + ('...' if len(msg.content) > 200 else ''),
                        'timestamp': msg.created_at.isoformat()
                    } for msg in matching_messages
                ]
            })
        
        return JsonResponse({
            'success': True,
            'results': results,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
                'total_count': paginator.count
            },
            'query': query
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la recherche: {str(e)}'
        })


@require_http_methods(["GET"])
@login_required
def download_report(request, filename):
    """
    Télécharge un rapport généré
    """
    try:
        # Sécuriser le chemin du fichier
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(settings.MEDIA_ROOT, 'reports', safe_filename)
        
        if not os.path.exists(file_path):
            return JsonResponse({
                'success': False,
                'error': 'Fichier introuvable'
            })
        
        # Déterminer le type de contenu
        if safe_filename.endswith('.pdf'):
            content_type = 'application/pdf'
        elif safe_filename.endswith('.xlsx'):
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            content_type = 'application/octet-stream'
        
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
            return response
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors du téléchargement: {str(e)}'
        })


# =============================================================================
# VUES POUR LES CONVERSATIONS ENTRE UTILISATEURS
# =============================================================================

@login_required
def conversations_list(request):
    """
    Liste des conversations de l'utilisateur
    """
    conversations = Conversation.objects.filter(
        participants=request.user,
        is_active=True
    ).order_by('-updated_at')
    
    context = {
        'conversations': conversations,
        'user': request.user,
    }
    
    return render(request, 'chatbot/conversations_list.html', context)


@require_http_methods(["GET"])
@login_required
def api_conversations_list(request):
    """
    API pour lister les conversations
    """
    try:
        page = int(request.GET.get('page', 1))
        search = request.GET.get('search', '').strip()
        
        conversations = Conversation.objects.filter(
            participants=request.user,
            is_active=True
        )
        
        if search:
            conversations = conversations.filter(
                Q(title__icontains=search) |
                Q(conversation_messages__content__icontains=search)
            ).distinct()
        
        conversations = conversations.order_by('-updated_at')
        
        paginator = Paginator(conversations, 20)
        page_obj = paginator.get_page(page)
        
        conversations_data = []
        for conv in page_obj:
            last_message = conv.last_message
            unread_count = conv.conversation_messages.filter(
                created_at__gt=conv.participants_info.filter(
                    user=request.user
                ).first().last_read_at or timezone.now() - timedelta(days=365)
            ).exclude(sender=request.user).count()
            
            conversations_data.append({
                'id': conv.id,
                'title': conv.title or str(conv),
                'type': conv.conversation_type,
                'participants_count': conv.participants.count(),
                'last_message': {
                    'content': last_message.content[:100] + ('...' if len(last_message.content) > 100 else '') if last_message else None,
                    'sender': last_message.sender.get_full_name() or last_message.sender.username if last_message else None,
                    'created_at': last_message.created_at.isoformat() if last_message else None
                },
                'unread_count': unread_count,
                'updated_at': conv.updated_at.isoformat(),
                'created_at': conv.created_at.isoformat()
            })
        
        return JsonResponse({
            'success': True,
            'conversations': conversations_data,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
                'total_count': paginator.count
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@login_required
def conversation_detail(request, conversation_id):
    """
    Détail d'une conversation
    """
    try:
        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=request.user,
            is_active=True
        )
        
        # Marquer comme lu
        participant = conversation.participants_info.filter(user=request.user).first()
        if participant:
            participant.last_read_at = timezone.now()
            participant.save()
        
        context = {
            'conversation': conversation,
            'user': request.user,
        }
        
        return render(request, 'chatbot/conversation_detail.html', context)
        
    except Exception as e:
        return render(request, 'chatbot/error.html', {
            'error_message': f'Erreur lors du chargement de la conversation: {str(e)}'
        })


@require_http_methods(["GET"])
@login_required
def api_conversation_messages(request, conversation_id):
    """
    API pour récupérer les messages d'une conversation
    """
    try:
        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=request.user,
            is_active=True
        )
        
        page = int(request.GET.get('page', 1))
        messages = conversation.conversation_messages.order_by('created_at')
        
        paginator = Paginator(messages, 50)
        page_obj = paginator.get_page(page)
        
        messages_data = []
        for message in page_obj:
            messages_data.append({
                'id': message.id,
                'sender': {
                    'id': message.sender.id,
                    'username': message.sender.username,
                    'full_name': message.sender.get_full_name() or message.sender.username
                },
                'content': message.content,
                'message_type': message.message_type,
                'file_attachment': message.file_attachment.url if message.file_attachment else None,
                'reply_to': {
                    'id': message.reply_to.id,
                    'content': message.reply_to.content[:50] + '...' if len(message.reply_to.content) > 50 else message.reply_to.content
                } if message.reply_to else None,
                'is_edited': message.is_edited,
                'edited_at': message.edited_at.isoformat() if message.edited_at else None,
                'created_at': message.created_at.isoformat(),
                'reactions': [{
                    'reaction': reaction.reaction,
                    'count': message.reactions.filter(reaction=reaction.reaction).count(),
                    'users': [{
                        'username': user.username,
                        'full_name': user.get_full_name() or user.username
                    } for user in User.objects.filter(
                        messagereaction__message=message,
                        messagereaction__reaction=reaction.reaction
                    )]
                } for reaction in message.reactions.values('reaction').distinct()]
            })
        
        return JsonResponse({
            'success': True,
            'messages': messages_data,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
                'total_count': paginator.count
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_send_conversation_message(request, conversation_id):
    """
    API pour envoyer un message dans une conversation
    """
    try:
        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=request.user,
            is_active=True
        )
        
        data = json.loads(request.body)
        content = data.get('content', '').strip()
        message_type = data.get('message_type', 'text')
        reply_to_id = data.get('reply_to')
        
        if not content:
            return JsonResponse({
                'success': False,
                'error': 'Message vide'
            })
        
        # Vérifier si c'est une réponse à un message
        reply_to = None
        if reply_to_id:
            try:
                reply_to = ConversationMessage.objects.get(
                    id=reply_to_id,
                    conversation=conversation
                )
            except ConversationMessage.DoesNotExist:
                pass
        
        # Créer le message
        message = ConversationMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content,
            message_type=message_type,
            reply_to=reply_to
        )
        
        # Mettre à jour la conversation
        conversation.updated_at = timezone.now()
        conversation.save()
        
        return JsonResponse({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'sender': {
                    'id': message.sender.id,
                    'username': message.sender.username,
                    'full_name': message.sender.get_full_name() or message.sender.username
                },
                'message_type': message.message_type,
                'reply_to': {
                    'id': message.reply_to.id,
                    'content': message.reply_to.content[:50] + '...' if len(message.reply_to.content) > 50 else message.reply_to.content
                } if message.reply_to else None,
                'created_at': message.created_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_create_conversation(request):
    """
    API pour créer une nouvelle conversation
    """
    print(f"=== DEBUG: Création conversation par {request.user.username} ===")
    try:
        print(f"Request body: {request.body}")
        data = json.loads(request.body)
        print(f"Data parsed: {data}")
        
        title = data.get('title', '').strip()
        conversation_type = data.get('type', 'private')
        participant_ids = data.get('participants', [])
        
        print(f"Title: {title}")
        print(f"Type: {conversation_type}")
        print(f"Participant IDs: {participant_ids}")
        
        if not participant_ids:
            print("ERREUR: Aucun participant spécifié")
            return JsonResponse({
                'success': False,
                'error': 'Aucun participant spécifié'
            })
        
        # Vérifier que les participants existent
        participants = User.objects.filter(id__in=participant_ids)
        if participants.count() != len(participant_ids):
            return JsonResponse({
                'success': False,
                'error': 'Certains participants sont introuvables'
            })
        
        # Créer la conversation
        conversation = Conversation.objects.create(
            title=title,
            conversation_type=conversation_type,
            created_by=request.user
        )
        
        # Ajouter les participants
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=request.user,
            role='owner'
        )
        
        for participant in participants:
            if participant != request.user:
                ConversationParticipant.objects.create(
                    conversation=conversation,
                    user=participant,
                    role='member'
                )
        
        return JsonResponse({
            'success': True,
            'conversation': {
                'id': conversation.id,
                'title': conversation.title or str(conversation),
                'type': conversation.conversation_type,
                'participants_count': conversation.participants.count(),
                'created_at': conversation.created_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_add_reaction(request, message_id):
    """
    API pour ajouter/enlever une réaction à un message
    """
    try:
        data = json.loads(request.body)
        reaction = data.get('reaction')
        
        if not reaction:
            return JsonResponse({
                'success': False,
                'error': 'Réaction manquante'
            })
        
        message = get_object_or_404(
            ConversationMessage,
            id=message_id,
            conversation__participants=request.user
        )
        
        # Vérifier si la réaction existe déjà
        existing_reaction = MessageReaction.objects.filter(
            message=message,
            user=request.user,
            reaction=reaction
        ).first()
        
        if existing_reaction:
            # Enlever la réaction
            existing_reaction.delete()
            action = 'removed'
        else:
            # Ajouter la réaction
            MessageReaction.objects.create(
                message=message,
                user=request.user,
                reaction=reaction
            )
            action = 'added'
        
        # Compter les réactions
        reaction_count = message.reactions.filter(reaction=reaction).count()
        
        return JsonResponse({
            'success': True,
            'action': action,
            'reaction': reaction,
            'count': reaction_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


# =============================================================================
# GESTION AVANCÉE DES GROUPES
# =============================================================================

@require_http_methods(["GET"])
@login_required
def api_conversation_participants(request, conversation_id):
    """
    API pour récupérer les participants d'une conversation
    """
    try:
        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=request.user,
            is_active=True
        )
        
        participants_data = []
        for participant_info in conversation.participants_info.all():
            user = participant_info.user
            participants_data.append({
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name() or user.username,
                'email': user.email,
                'role': participant_info.role,
                'joined_at': participant_info.joined_at.isoformat(),
                'last_read_at': participant_info.last_read_at.isoformat() if participant_info.last_read_at else None,
                'notifications_enabled': participant_info.notifications_enabled,
                'is_current_user': user.id == request.user.id
            })
        
        return JsonResponse({
            'success': True,
            'participants': participants_data,
            'conversation': {
                'id': conversation.id,
                'title': conversation.title,
                'type': conversation.conversation_type,
                'created_by': conversation.created_by.id == request.user.id
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_add_participant(request, conversation_id):
    """
    API pour ajouter un participant à une conversation de groupe
    """
    try:
        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=request.user,
            is_active=True
        )
        
        # Vérifier que c'est un groupe
        if conversation.conversation_type != 'group':
            return JsonResponse({
                'success': False,
                'error': 'Seuls les groupes peuvent avoir des participants ajoutés'
            })
        
        # Vérifier les permissions (propriétaire ou admin)
        user_participant = conversation.participants_info.filter(user=request.user).first()
        if not user_participant or user_participant.role not in ['owner', 'admin']:
            return JsonResponse({
                'success': False,
                'error': 'Permissions insuffisantes pour ajouter des participants'
            })
        
        data = json.loads(request.body)
        user_id = data.get('user_id')
        role = data.get('role', 'member')
        
        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'ID utilisateur manquant'
            })
        
        # Vérifier que l'utilisateur existe
        try:
            user_to_add = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Utilisateur introuvable'
            })
        
        # Vérifier qu'il n'est pas déjà participant
        if conversation.participants.filter(id=user_id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Cet utilisateur est déjà membre du groupe'
            })
        
        # Ajouter le participant
        ConversationParticipant.objects.create(
            conversation=conversation,
            user=user_to_add,
            role=role
        )
        
        # Message système pour notifier l'ajout
        ConversationMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            content=f"{user_to_add.get_full_name() or user_to_add.username} a été ajouté au groupe",
            message_type='system'
        )
        
        conversation.updated_at = timezone.now()
        conversation.save()
        
        return JsonResponse({
            'success': True,
            'message': f'{user_to_add.get_full_name() or user_to_add.username} ajouté au groupe'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_remove_participant(request, conversation_id, user_id):
    """
    API pour retirer un participant d'une conversation de groupe
    """
    try:
        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=request.user,
            is_active=True
        )
        
        # Vérifier que c'est un groupe
        if conversation.conversation_type != 'group':
            return JsonResponse({
                'success': False,
                'error': 'Seuls les participants des groupes peuvent être retirés'
            })
        
        # Vérifier les permissions
        user_participant = conversation.participants_info.filter(user=request.user).first()
        target_participant = conversation.participants_info.filter(user_id=user_id).first()
        
        if not target_participant:
            return JsonResponse({
                'success': False,
                'error': 'Participant introuvable'
            })
        
        # Le propriétaire peut retirer n'importe qui (sauf lui-même)
        # Un admin peut retirer des membres (pas d'autres admins ou le propriétaire)
        # Un membre ne peut se retirer que lui-même
        can_remove = False
        
        if user_participant.role == 'owner' and target_participant.user.id != request.user.id:
            can_remove = True
        elif user_participant.role == 'admin' and target_participant.role == 'member':
            can_remove = True
        elif target_participant.user.id == request.user.id:
            can_remove = True
        
        if not can_remove:
            return JsonResponse({
                'success': False,
                'error': 'Permissions insuffisantes pour retirer ce participant'
            })
        
        # Retirer le participant
        user_name = target_participant.user.get_full_name() or target_participant.user.username
        target_participant.delete()
        
        # Message système pour notifier le retrait
        if target_participant.user.id == request.user.id:
            message = f"{user_name} a quitté le groupe"
        else:
            message = f"{user_name} a été retiré du groupe"
            
        ConversationMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            content=message,
            message_type='system'
        )
        
        conversation.updated_at = timezone.now()
        conversation.save()
        
        return JsonResponse({
            'success': True,
            'message': f'{user_name} retiré du groupe'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })


@require_http_methods(["GET"])
@login_required
def api_search_users(request):
    """
    API pour rechercher des utilisateurs (pour les invitations)
    """
    try:
        query = request.GET.get('q', '').strip()
        
        if len(query) < 2:
            return JsonResponse({
                'success': False,
                'error': 'Requête de recherche trop courte'
            })
        
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        ).exclude(id=request.user.id)[:10]
        
        users_data = []
        for user in users:
            users_data.append({
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name() or user.username,
                'email': user.email
            })
        
        return JsonResponse({
            'success': True,
            'users': users_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })
