from django.contrib import admin

from .models import GeoPositionAudit, Repere, ReperePhoto, TypeRepere


@admin.register(TypeRepere)
class TypeRepereAdmin(admin.ModelAdmin):
    list_display = ('nom', 'icone', 'couleur', 'ordre_affichage', 'actif', 'updated_at')
    list_editable = ('ordre_affichage', 'actif')
    search_fields = ('nom', 'description')


@admin.register(Repere)
class RepereAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_repere', 'ouvrage', 'organisation', 'createur', 'version', 'archived_at', 'updated_at')
    list_filter = ('type_repere', 'organisation', 'archived_at')
    search_fields = ('nom', 'remarques')
    readonly_fields = ('version', 'created_at', 'updated_at')


@admin.register(ReperePhoto)
class ReperePhotoAdmin(admin.ModelAdmin):
    list_display = ('repere', 'nom', 'taille', 'mime_type', 'createur', 'created_at')
    readonly_fields = ('local_uuid', 'taille', 'sha256', 'created_at')


@admin.register(GeoPositionAudit)
class GeoPositionAuditAdmin(admin.ModelAdmin):
    list_display = ('entity_kind', 'entity_uuid', 'utilisateur', 'capture_method', 'captured_at', 'received_at')
    list_filter = ('entity_kind', 'capture_method')
    search_fields = ('entity_uuid', 'local_uuid', 'utilisateur__username')
    readonly_fields = [field.name for field in GeoPositionAudit._meta.fields]
