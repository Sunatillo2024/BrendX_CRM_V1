from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import PinAttempt, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'first_name', 'last_name', 'role', 'is_active', 'pin_status']
    list_filter = ['role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('BrandX Profile', {'fields': ('role', 'phone', 'avatar', 'language')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('BrandX Profile', {'fields': ('role', 'phone', 'language')}),
    )

    @admin.display(boolean=True, description='PIN set')
    def pin_status(self, obj):
        return obj.has_pin


@admin.register(PinAttempt)
class PinAttemptAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'ip_address', 'was_success']
    list_filter = ['was_success', 'created_at']

    def has_add_permission(self, request):
        return False
