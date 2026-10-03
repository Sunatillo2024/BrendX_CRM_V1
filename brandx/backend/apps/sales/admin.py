from django.contrib import admin

from .models import Receipt, Sale, SaleItem, SaleReturn, SaleReturnItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ['product_name', 'color_name', 'size_name', 'discount_amount', 'total_price']
    fields = ['product_variant', 'product_name', 'color_name', 'size_name', 'quantity',
              'unit_price', 'unit_cost', 'discount_percent', 'discount_amount', 'total_price']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['sale_number', 'created_at', 'cashier', 'customer', 'payment_method',
                    'total_amount', 'cash_amount', 'card_amount', 'change_amount', 'status']
    list_filter = ['payment_method', 'status', 'created_at', 'cashier']
    search_fields = ['number', 'customer__name', 'notes']
    readonly_fields = ['number', 'created_at', 'updated_at']
    inlines = [SaleItemInline]

    @admin.display(description='№')
    def sale_number(self, obj):
        return obj.sale_number


class SaleReturnItemInline(admin.TabularInline):
    model = SaleReturnItem
    extra = 0


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ['id', 'sale', 'reason', 'total_amount', 'created_by', 'created_at']
    list_filter = ['reason', 'created_at']
    search_fields = ['sale__number', 'notes']
    inlines = [SaleReturnItemInline]


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'sale', 'generated_at', 'printed_count']
    search_fields = ['receipt_number', 'sale__number']
