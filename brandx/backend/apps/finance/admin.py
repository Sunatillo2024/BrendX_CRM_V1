from django.contrib import admin

from .models import FinanceEntry


@admin.register(FinanceEntry)
class FinanceEntryAdmin(admin.ModelAdmin):
    list_display = ['entry_date', 'entry_type', 'category', 'amount', 'created_by']
    list_filter = ['entry_type', 'category', 'entry_date']
    search_fields = ['category', 'comment']
    readonly_fields = ['created_at', 'updated_at']
