"""
Sales Models.

One sale = one receipt. Payment is cash, card or mixed (cash + card).
Credit / installment sales were intentionally removed.
"""
from decimal import Decimal

from django.db import models
from apps.stores.models import StoreOwned
from django.utils.translation import gettext_lazy as _

CENTS = Decimal('0.01')


def _dec(value):
    """Coerce ints/floats/None into Decimal so money math never mixes types."""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class Sale(StoreOwned):
    """Core sale transaction (POS check)."""

    PAYMENT_CASH = 'cash'
    PAYMENT_CARD = 'card'
    PAYMENT_MIXED = 'mixed'

    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Cash'),
        (PAYMENT_CARD, 'Card'),
        (PAYMENT_MIXED, 'Mixed'),
    ]

    STATUS_COMPLETED = 'completed'
    STATUS_PARTIALLY_REFUNDED = 'partially_refunded'
    STATUS_REFUNDED = 'refunded'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_PARTIALLY_REFUNDED, 'Partially refunded'),
        (STATUS_REFUNDED, 'Refunded'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    # Sequential receipt number (Чек №000124)
    number = models.PositiveIntegerField()
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sales'
    )
    cashier = models.ForeignKey(
        'authentication.User', on_delete=models.PROTECT, related_name='sales'
    )

    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_CHOICES, default=PAYMENT_CASH, db_index=True
    )
    subtotal = models.DecimalField(max_digits=15, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)

    # Payment breakdown
    cash_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    card_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    received_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text='Amount handed over by the customer.'
    )
    change_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text='Change given back.'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED,
                              db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales'
        verbose_name = _('Sale')
        verbose_name_plural = _('Sales')
        ordering = ['-created_at']
        indexes = [models.Index(fields=['store', 'status', '-created_at'])]
        constraints = [models.UniqueConstraint(fields=['store', 'number'], name='sale_store_number')]

    def __str__(self):
        return f'{self.sale_number} - {self.total_amount}'

    @property
    def sale_number(self):
        """Display number, e.g. 000124."""
        return f'{self.number:06d}'

    @property
    def receipt_number(self):
        return self.sale_number

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    @classmethod
    def next_number(cls, *, store):
        return store.next_number('sale')


class SaleItem(models.Model):
    """
    Sale line.

    Product name / colour / size and the purchase cost are snapshotted so that
    the receipt and the profit reports never change when the catalog changes.
    """
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(
        'products.ProductVariant', on_delete=models.PROTECT, related_name='sale_items'
    )
    product_name = models.CharField(max_length=200)
    color_name = models.CharField(max_length=50, blank=True)
    size_name = models.CharField(max_length=20, blank=True)

    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                    help_text='Purchase cost snapshot (owner-only in the API).')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=15, decimal_places=2)

    returned_quantity = models.IntegerField(default=0)

    class Meta:
        db_table = 'sale_items'
        verbose_name = _('Sale item')
        verbose_name_plural = _('Sale items')
        ordering = ['id']

    def __str__(self):
        return f'{self.sale.sale_number} - {self.product_name} x{self.quantity}'

    def save(self, *args, **kwargs):
        line_total = _dec(self.unit_price) * self.quantity
        percent = _dec(self.discount_percent)
        self.discount_amount = (line_total * percent / Decimal('100')).quantize(CENTS)
        self.total_price = line_total - self.discount_amount
        super().save(*args, **kwargs)


class Receipt(models.Model):
    """Printed receipt record for a sale."""
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name='receipt')
    receipt_number = models.CharField(max_length=30)
    generated_at = models.DateTimeField(auto_now_add=True)
    printed_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'receipts'
        verbose_name = _('Receipt')
        verbose_name_plural = _('Receipts')
        ordering = ['-generated_at']

    def __str__(self):
        return f'{self.receipt_number} - {self.sale.sale_number}'


class SaleReturn(models.Model):
    """Goods returned by a customer. The original sale is never deleted."""
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    reason = models.CharField(max_length=20, choices=[
        ('size', 'Wrong size'),
        ('defect', 'Defect'),
        ('change_mind', 'Customer changed mind'),
        ('other', 'Other'),
    ], default='other')
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cash_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    card_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, null=True, related_name='sale_returns'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'sale_returns'
        verbose_name = _('Sale return')
        verbose_name_plural = _('Sale returns')
        ordering = ['-created_at']

    def __str__(self):
        return f'Return #{self.pk} for {self.sale.sale_number}'

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())


class SaleReturnItem(models.Model):
    """One returned line."""
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name='return_items')
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = 'sale_return_items'
        verbose_name = _('Sale return item')
        verbose_name_plural = _('Sale return items')

    def __str__(self):
        return f'{self.sale_item.product_name} x{self.quantity}'

    def save(self, *args, **kwargs):
        self.total_price = _dec(self.unit_price) * self.quantity
        super().save(*args, **kwargs)
