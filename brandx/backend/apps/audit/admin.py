from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'username', 'action', 'entity', 'entity_id']
    list_filter = ['action', 'entity', 'created_at']
    search_fields = ['username', 'entity', 'entity_id']
    readonly_fields = ['user', 'username', 'action', 'entity', 'entity_id', 'details', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
