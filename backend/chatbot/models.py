from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import uuid


class ChatSession(models.Model):
    """
    Modèle pour les sessions de chat
    Correspond à la table chat_sessions dans Supabase
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                            verbose_name="Utilisateur")
    started_at = models.DateTimeField(default=timezone.now, verbose_name="Démarré à")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="Terminé à")
    title = models.TextField(blank=True, verbose_name="Titre de la conversation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Session de chat"
        verbose_name_plural = "Sessions de chat"
        ordering = ['-started_at']
        db_table = 'chat_sessions'
    
    def __str__(self):
        return f"Session {self.id} - {self.title[:50] if self.title else 'Sans titre'}"
    
    @property
    def is_active(self):
        """Indique si la session est encore active"""
        return self.ended_at is None
    
    @property
    def message_count(self):
        """Retourne le nombre de messages dans cette session"""
        return self.messages.count()
    
    def generate_title_from_first_message(self):
        """Génère un titre basé sur le premier message utilisateur"""
        first_message = self.messages.filter(role='user').first()
        if first_message:
            content = first_message.content
            self.title = content[:50] + ('...' if len(content) > 50 else '')
        else:
            self.title = f"Nouvelle conversation ({self.message_count} messages)"
        self.save()
        return self.title


class ChatMessage(models.Model):
    """
    Modèle pour les messages de chat
    Correspond à la table chat_messages dans Supabase
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ROLE_CHOICES = [
        ('user', 'Utilisateur'),
        ('assistant', 'Assistant'),
        ('system', 'Système'),
    ]
    
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, 
                               related_name='messages', verbose_name="Session")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name="Rôle")
    content = models.TextField(verbose_name="Contenu")
    metadata = models.JSONField(default=dict, blank=True, 
                               help_text="Métadonnées additionnelles (graphiques, fichiers, etc.)")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Message de chat"
        verbose_name_plural = "Messages de chat"
        ordering = ['created_at']
        db_table = 'chat_messages'
    
    def __str__(self):
        return f"{self.get_role_display()}: {self.content[:50]}..."
    
    @property
    def has_chart(self):
        """Indique si le message contient des données de graphique"""
        return 'chart_data' in self.metadata
    
    @property
    def has_files(self):
        """Indique si le message contient des fichiers générés"""
        return 'generated_files' in self.metadata
    
    @property
    def chart_data(self):
        """Retourne les données de graphique si disponibles"""
        return self.metadata.get('chart_data', {})
    
    @property
    def generated_files(self):
        """Retourne la liste des fichiers générés"""
        return self.metadata.get('generated_files', [])


class Conversation(models.Model):
    """
    Modèle pour les conversations entre utilisateurs
    """
    TYPE_CHOICES = [
        ('private', 'Conversation privée'),
        ('group', 'Conversation de groupe'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, blank=True, verbose_name="Titre")
    conversation_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='private', verbose_name="Type")
    participants = models.ManyToManyField(User, through='ConversationParticipant', verbose_name="Participants")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_conversations', verbose_name="Créé par")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, verbose_name="Active")
    
    class Meta:
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"
        ordering = ['-updated_at']
        db_table = 'conversations'
    
    def __str__(self):
        if self.title:
            return self.title
        participants_names = ", ".join([p.get_full_name() or p.username for p in self.participants.all()[:3]])
        return f"Conversation: {participants_names}{'...' if self.participants.count() > 3 else ''}"
    
    @property
    def last_message(self):
        """Retourne le dernier message de la conversation"""
        return self.conversation_messages.order_by('-created_at').first()
    
    @property
    def unread_count_for_user(self, user):
        """Retourne le nombre de messages non lus pour un utilisateur"""
        participant = self.participants_info.filter(user=user).first()
        if not participant:
            return 0
        return self.conversation_messages.filter(
            created_at__gt=participant.last_read_at or timezone.now() - timedelta(days=365)
        ).exclude(sender=user).count()


class ConversationParticipant(models.Model):
    """
    Modèle intermédiaire pour les participants aux conversations
    """
    ROLE_CHOICES = [
        ('member', 'Membre'),
        ('admin', 'Administrateur'),
        ('owner', 'Propriétaire'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='participants_info')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member', verbose_name="Rôle")
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True, verbose_name="Dernière lecture")
    notifications_enabled = models.BooleanField(default=True, verbose_name="Notifications activées")
    
    class Meta:
        verbose_name = "Participant de conversation"
        verbose_name_plural = "Participants de conversation"
        unique_together = ['conversation', 'user']
        db_table = 'conversation_participants'
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.conversation}"


class ConversationMessage(models.Model):
    """
    Modèle pour les messages dans les conversations entre utilisateurs
    """
    MESSAGE_TYPE_CHOICES = [
        ('text', 'Texte'),
        ('file', 'Fichier'),
        ('image', 'Image'),
        ('system', 'Message système'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='conversation_messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Expéditeur")
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='text', verbose_name="Type")
    content = models.TextField(verbose_name="Contenu")
    file_attachment = models.FileField(upload_to='conversation_files/', null=True, blank=True, verbose_name="Fichier joint")
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Réponse à")
    is_edited = models.BooleanField(default=False, verbose_name="Modifié")
    edited_at = models.DateTimeField(null=True, blank=True, verbose_name="Modifié le")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Message de conversation"
        verbose_name_plural = "Messages de conversation"
        ordering = ['created_at']
        db_table = 'conversation_messages'
    
    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}..."
    
    def mark_as_read_by(self, user):
        """Marque le message comme lu par un utilisateur"""
        participant = self.conversation.participants_info.filter(user=user).first()
        if participant:
            participant.last_read_at = timezone.now()
            participant.save()


class MessageReaction(models.Model):
    """
    Modèle pour les réactions aux messages
    """
    REACTION_CHOICES = [
        ('👍', 'Pouce en l\'air'),
        ('❤️', 'Cœur'),
        ('😂', 'Rire'),
        ('😮', 'Surpris'),
        ('😢', 'Triste'),
        ('😡', 'Colère'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(ConversationMessage, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reaction = models.CharField(max_length=10, choices=REACTION_CHOICES, verbose_name="Réaction")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Réaction"
        verbose_name_plural = "Réactions"
        unique_together = ['message', 'user', 'reaction']
        db_table = 'message_reactions'
    
    def __str__(self):
        return f"{self.user.username} - {self.reaction} sur message {self.message.id}"
