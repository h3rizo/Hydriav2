from django.contrib import admin
from .models import Tag, FileUpload


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']


@admin.register(FileUpload)
class FileUploadAdmin(admin.ModelAdmin):
    list_display = ['filename', 'file_size_mb', 'uploaded_by', 'uploaded_at', 'is_active']
    list_filter = ['content_type', 'is_public', 'is_active', 'uploaded_at', 'tags']
    search_fields = ['filename', 'original_filename', 'description']
    filter_horizontal = ['tags']
    readonly_fields = ['id', 'file_size', 'uploaded_at', 'supabase_path']
    
    def file_size_mb(self, obj):
        return f"{obj.file_size_mb} MB"
    file_size_mb.short_description = "Taille"
