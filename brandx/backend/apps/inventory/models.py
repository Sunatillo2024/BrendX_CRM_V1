"""
Inventory Models.

Product stock lives on ProductVariant.stock_quantity (single source of truth).
This app records *how* it changed:
  - StockReceipt      : a goods receipt document (Поступление №32)
  - StockReceiptItem  : one line of that document (variant + qty + purchase price)
  - StockMovement     : audit trail of every quantity change
"""
from django.db import models
from apps.stores.models import StoreOwned
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class StockReceipt(StoreOwned):
    """Goods receipt document: stock in from a vendor."""
    number = models.PositiveIntegerField()
    receipt_date = models.DateField(default=timezone.localdate, db_index=True)
    vendor = models.ForeignKey(
        'vendors.Vendor', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='receipts'
    )
    notes = models.TextField(blank=True)
    total_quantity = models.IntegerField(default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, null=True, related_name='receipts'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_receipts'
        verbose_name = _('Stock receipt')
        verbose_name_plural = _('Stock receipts')
        ordering = ['-number']
        constraints = [models.UniqueConstraint(fields=['store', 'number'], name='stock_receipt_store_number')]
        indexes = [models.Index(fields=['store', '-receipt_date'])]

    def __str__(self):
        return f'Поступление №{self.number}'

    @classmethod
    def next_number(cls, *, store):
        return store.next_number('receipt')

    def recalculate_totals(self):
        agg = self.items.aggregate(
            qty=models.Sum('quantity'), cost=models.Sum('total_cost')
        )
        self.total_quantity = agg['qty'] or 0
        self.total_cost = agg['cost'] or 0
        self.save(update_fields=['total_quantity', 'total_cost'])


class StockReceiptItem(models.Model):
    """One line of a goods receipt."""
    receipt = models.ForeignKey(StockReceipt, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(
        'products.ProductVariant', on_delete=models.PROTECT, related_name='receipt_items'
    )
    quantity = models.IntegerField()
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        db_table = 'stock_receipt_items'
        verbose_name = _('Stock receipt item')
        verbose_name_plural = _('Stock receipt items')
        ordering = ['id']

    def __str__(self):
        return f'{self.receipt} - {self.product_variant} +{self.quantity}'

    def save(self, *args, **kwargs):
        self.total_cost = self.cost_price * self.quantity
        super().save(*args, **kwargs)


class StockMovement(models.Model):
    """
    Every stock change is recorded here - nothing may change stock silently.

    quantity_before / quantity_change / quantity_after make the trail readable:
    "was 10, changed -2, now 8".
    """
    TYPE_PURCHASE = 'purchase'
    TYPE_SALE = 'sale'
    TYPE_RETURN = 'return'
    TYPE_ADJUSTMENT = 'adjustment'
    TYPE_INVENTORY = 'inventory'

    MOVEMENT_TYPES = [
        (TYPE_PURCHASE, 'Purchase'),
        (TYPE_SALE, 'Sale'),
        (TYPE_RETURN, 'Return'),
        (TYPE_ADJUSTMENT, 'Adjustment'),
        (TYPE_INVENTORY, 'Inventory count'),
    ]

    REASON_CHOICES = [
        ('', '—'),
        ('damage', 'Damage'),
        ('loss', 'Loss / theft'),
        ('return', 'Customer return'),
        ('inventory', 'Inventory count'),
        ('gift', 'Gift / sample'),
        ('correction', 'Correction'),
        ('other', 'Other'),
    ]

    product_variant = models.ForeignKey(
        'products.ProductVariant', on_delete=models.PROTECT, related_name='movements'
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, db_index=True)
    quantity_before = models.IntegerField()
    quantity_change = models.IntegerField()
    quantity_after = models.IntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, blank=True)
    reference = models.CharField(max_length=50, blank=True)
    receipt = models.ForeignKey(
        StockReceipt, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements'
    )
    sale = models.ForeignKey(
        'sales.Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='movements'
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, null=True, related_name='movements'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'stock_movements'
        verbose_name = _('Stock movement')
        verbose_name_plural = _('Stock movements')
        ordering = ['-created_at']
        indexes = [models.Index(fields=['product_variant', '-created_at'])]

    def __str__(self):
        sign = '+' if self.quantity_change >= 0 else ''
        return f'{self.product_variant} {sign}{self.quantity_change} ({self.movement_type})'
