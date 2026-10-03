from django.contrib import admin

from .models import StockMovement, StockReceipt, StockReceiptItem


class StockReceiptItemInline(admin.TabularInline):
    model = StockReceiptItem
    extra = 0
    readonly_fields = ['total_cost']


@admin.register(StockReceipt)
class StockReceiptAdmin(admin.ModelAdmin):
    list_display = ['number', 'receipt_date', 'vendor', 'total_quantity', 'total_cost', 'created_by']
    list_filter = ['receipt_date', 'vendor']
    search_fields = ['notes', 'vendor__name']
    readonly_fields = ['number', 'total_quantity', 'total_cost', 'created_at']
    inlines = [StockReceiptItemInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'product_variant', 'movement_type',
                    'quantity_before', 'quantity_change', 'quantity_after', 'created_by']
    list_filter = ['movement_type', 'reason', 'created_at']
    search_fields = ['reference', 'product_variant__product__name', 'product_variant__barcode']
    readonly_fields = ['created_at']
