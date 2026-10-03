from django.contrib import admin
from .models import Category, Color, Size, Product, ProductVariant


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']
    readonly_fields = ['created_at']


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ['name', 'hex_code']
    search_fields = ['name']


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ['name', 'size_type', 'display_order']
    list_filter = ['size_type']
    search_fields = ['name']


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    readonly_fields = ['created_at']
    fields = ['color', 'size', 'sku', 'barcode', 'selling_price', 'cost_price',
              'stock_quantity', 'low_stock_threshold', 'is_active']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'barcode', 'base_selling_price', 'base_cost_price', 'is_active', 'created_at']
    list_filter = ['is_active', 'category']
    search_fields = ['name', 'barcode']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ProductVariantInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'color', 'size', 'sku', 'barcode', 'selling_price',
                    'cost_price', 'stock_quantity', 'is_active']
    list_filter = ['is_active', 'color', 'size']
    search_fields = ['product__name', 'sku', 'barcode']
    readonly_fields = ['created_at']
