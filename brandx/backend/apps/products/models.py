"""Products App Models - Categories, Colors, Sizes, Products, Variants with Barcodes"""
import os
import uuid

from django.db import models
from apps.stores.models import StoreOwned
from django.utils.translation import gettext_lazy as _


def product_image_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'products/{uuid.uuid4()}{ext}'


def category_image_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'categories/{uuid.uuid4()}{ext}'


class Category(StoreOwned):
    """
    Product category (flat).

    Categories are managed by the
    owner/manager in the UI - they are never hard-coded in the application.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to=category_image_path, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['store', 'name'], name='%(class)s_store_name')]

    def __str__(self):
        return self.name


class Color(StoreOwned):
    """Colour options for product variants."""
    name = models.CharField(max_length=50)
    hex_code = models.CharField(max_length=7, default='#000000')

    class Meta:
        db_table = 'colors'
        verbose_name = _('Color')
        verbose_name_plural = _('Colors')
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['store', 'name'], name='%(class)s_store_name')]

    def __str__(self):
        return self.name


class Size(StoreOwned):
    """Size options for product variants (S/M/L, numeric, universal)."""
    SIZE_LETTER = 'letter'
    SIZE_NUMERIC = 'numeric'
    SIZE_AGE = 'age'
    SIZE_UNIVERSAL = 'universal'

    SIZE_TYPE_CHOICES = [
        (SIZE_LETTER, 'Letter (XS/S/M/L/XL/XXL)'),
        (SIZE_NUMERIC, 'Numeric (28/30/32/34)'),
        (SIZE_AGE, 'Age-based (2Y/4Y/6Y/8Y)'),
        (SIZE_UNIVERSAL, 'Universal'),
    ]

    name = models.CharField(max_length=20)
    size_type = models.CharField(max_length=20, choices=SIZE_TYPE_CHOICES)
    display_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'sizes'
        verbose_name = _('Size')
        verbose_name_plural = _('Sizes')
        ordering = ['size_type', 'display_order']
        unique_together = [['store', 'name', 'size_type']]

    def __str__(self):
        return self.name


class Product(StoreOwned):
    """
    Main product entity.
    Each product has one or more variants (colour + size combinations).
    """
    name = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products'
    )
    barcode = models.CharField(max_length=50)
    image = models.ImageField(upload_to=product_image_path, null=True, blank=True)
    # Purchase price (owner-only in the API) / sale price
    base_cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    base_selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    low_stock_threshold = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = _('Product')
        verbose_name_plural = _('Products')
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['store', 'name'], name='%(class)s_store_name')]
        indexes = [models.Index(fields=['store', 'is_active', 'name'])]
        constraints = [models.UniqueConstraint(fields=['store', 'barcode'], name='product_store_barcode')]

    def __str__(self):
        return self.name

    @property
    def total_stock(self):
        return sum(v.stock_quantity for v in self.variants.filter(is_active=True))


class ProductVariant(StoreOwned):
    """
    Product variant = product + colour + size.
    Own barcode, SKU, selling price and stock quantity.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    color = models.ForeignKey(
        Color, on_delete=models.SET_NULL, null=True, blank=True, related_name='variants'
    )
    size = models.ForeignKey(
        Size, on_delete=models.SET_NULL, null=True, blank=True, related_name='variants'
    )
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=50)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Latest purchase price for this variant (falls back to product base cost).'
    )
    stock_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_variants'
        verbose_name = _('Product variant')
        verbose_name_plural = _('Product variants')
        unique_together = [['product', 'color', 'size']]
        indexes = [models.Index(fields=['store', 'product', 'is_active'])]
        constraints = [
            models.UniqueConstraint(fields=['store', 'barcode'], name='variant_store_barcode'),
            models.UniqueConstraint(fields=['store', 'sku'], name='variant_store_sku'),
        ]

    def __str__(self):
        parts = [self.product.name]
        if self.color:
            parts.append(self.color.name)
        if self.size:
            parts.append(self.size.name)
        return ' - '.join(parts)

    @property
    def effective_price(self):
        return self.selling_price if self.selling_price is not None else self.product.base_selling_price

    @property
    def effective_cost(self):
        """Purchase price used for profit calculations (owner-only data)."""
        if self.cost_price is not None:
            return self.cost_price
        return self.product.base_cost_price

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.stock_quantity <= 0

    def generate_sku(self):
        parts = [self.product.barcode]
        if self.color:
            parts.append(self.color.name[:3].upper())
        if self.size:
            parts.append(self.size.name.upper())
        return '-'.join(parts)
