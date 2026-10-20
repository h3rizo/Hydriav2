from django.contrib import admin
from .models import ChatSession, ChatMessage, Conversation, ConversationParticipant, ConversationMessage, MessageReaction


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'started_at', 'ended_at', 'is_active', 'message_count']
    list_filter = ['started_at', 'ended_at']
    search_fields = ['title', 'user__username']
    readonly_fields = ['id', 'started_at', 'ended_at']

    def is_active(self, obj):
        return obj.is_active
    is_active.boolean = True
    is_active.short_description = "Active"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['session', 'role', 'content_preview', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['content', 'session__title']
    readonly_fields = ['id', 'created_at']

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = "Contenu"


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['title', 'conversation_type', 'created_by', 'participants_count', 'created_at', 'is_active']
    list_filter = ['conversation_type', 'is_active', 'created_at']
    search_fields = ['title', 'created_by__username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    # filter_horizontal ne peut pas être utilisé avec through model

    def participants_count(self, obj):
        return obj.participants.count()
    participants_count.short_description = "Participants"


@admin.register(ConversationParticipant)
class ConversationParticipantAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'user', 'role', 'joined_at', 'notifications_enabled']
    list_filter = ['role', 'joined_at', 'notifications_enabled']
    search_fields = ['conversation__title', 'user__username']
    readonly_fields = ['id', 'joined_at']


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'sender', 'message_type', 'content_preview', 'is_edited', 'created_at']
    list_filter = ['message_type', 'is_edited', 'created_at']
    search_fields = ['content', 'sender__username', 'conversation__title']
    readonly_fields = ['id', 'created_at', 'edited_at']

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = "Contenu"


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ['message_preview', 'user', 'reaction', 'created_at']
    list_filter = ['reaction', 'created_at']
    search_fields = ['message__content', 'user__username']
    readonly_fields = ['id', 'created_at']

    def message_preview(self, obj):
        return f"{obj.message.content[:30]}..." if len(obj.message.content) > 30 else obj.message.content
    message_preview.short_description = "Message"
