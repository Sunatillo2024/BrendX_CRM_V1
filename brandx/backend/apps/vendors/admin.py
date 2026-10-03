from django.contrib import admin
from .models import Vendor, VendorTransaction


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'company_name', 'balance', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'phone', 'email', 'company_name', 'tax_number']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(VendorTransaction)
class VendorTransactionAdmin(admin.ModelAdmin):
    list_display = ['vendor', 'transaction_type', 'amount', 'balance_after', 'date', 'created_by', 'created_at']
    list_filter = ['transaction_type', 'date']
    search_fields = ['vendor__name', 'reference']
    readonly_fields = ['created_at']
