from rest_framework import serializers

from .models import Note, NoteAttachment, NoteComment, NoteDecision, NoteLink, NoteTask, NoteVersion, Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'color', 'is_system']


class NoteLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteLink
        fields = ['id', 'entity_type', 'entity_id', 'label', 'created_at']


class NoteSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    links = NoteLinkSerializer(many=True, read_only=True)

    class Meta:
        model = Note
        fields = [
            'id', 'parent', 'title', 'note_type', 'status',
            'content_json', 'content_text', 'is_favorite', 'is_archived',
            'visibility', 'shared_with_base', 'visible_role_name', 'team_label',
            'created_by', 'updated_by', 'created_at', 'updated_at',
            'tags', 'links',
        ]


class NoteTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteTask
        fields = '__all__'


class NoteCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteComment
        fields = '__all__'


class NoteVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteVersion
        fields = '__all__'


class NoteDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteDecision
        fields = '__all__'


class NoteAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteAttachment
        fields = '__all__'
