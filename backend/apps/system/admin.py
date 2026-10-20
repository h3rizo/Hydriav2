from django.contrib import admin
from .models import SystemParameter, ActivityLog, PasswordResetCode, PageVisit, UserPresence, StorageSnapshot

@admin.register(SystemParameter)
class SystemParameterAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'category', 'updated_at')
    search_fields = ('key', 'value', 'description')
    list_filter = ('category',)

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'log_type', 'user', 'action', 'model_name')
    list_filter = ('log_type', 'created_at')
    search_fields = ('action', 'details', 'object_id')
    readonly_fields = ('created_at',)

@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(admin.ModelAdmin):
    list_display = ('email', 'code', 'created_at', 'is_used')
    list_filter = ('is_used', 'created_at')
    search_fields = ('email', 'code')

@admin.register(PageVisit)
class PageVisitAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'path', 'ip_address')
    list_filter = ('timestamp', 'path')
    search_fields = ('path', 'user__username', 'ip_address', 'user_agent')
    readonly_fields = ('timestamp',)

@admin.register(UserPresence)
class UserPresenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'path', 'last_seen')
    list_filter = ('last_seen', 'path')
    search_fields = ('user__username', 'path')
    readonly_fields = ('last_seen',)


@admin.register(StorageSnapshot)
class StorageSnapshotAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'root_path', 'used_percent', 'used_bytes', 'free_bytes')
    list_filter = ('root_path', 'created_at')
    search_fields = ('root_path',)
    readonly_fields = ('created_at',)
