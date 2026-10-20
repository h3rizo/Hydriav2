from rest_framework import serializers
from .models import File, Tag

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['name']

class FileSerializer(serializers.ModelSerializer):
    tags = serializers.StringRelatedField(many=True)
    
    class Meta:
        model = File
        fields = ['id', 'original_filename', 'file_size', 'mime_type', 'uploaded_at', 'tags']

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(write_only=True)
    tags = serializers.CharField(required=False, allow_blank=True)