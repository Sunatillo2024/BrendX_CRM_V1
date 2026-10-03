"""Vendors App Models - Vendor management with financial tracking"""
from django.db import models
from apps.stores.models import StoreOwned
from django.utils.translation import gettext_lazy as _


class Vendor(StoreOwned):
    """Supplier/vendor with financial balance tracking."""
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    contact_person = models.CharField(max_length=100, blank=True)
    company_name = models.CharField(max_length=200, blank=True)
    tax_number = models.CharField(max_length=50, blank=True)
    # Positive = we owe vendor, Negative = vendor owes us
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendors'
        verbose_name = _('Vendor')
        verbose_name_plural = _('Vendors')
        ordering = ['name']

    def __str__(self):
        return self.name


class VendorTransaction(models.Model):
    """
    Tracks all financial transactions with a vendor.
    Types: purchase (we buy), payment (we pay them), return (we return goods)
    """
    TYPE_PURCHASE = 'purchase'
    TYPE_PAYMENT = 'payment'
    TYPE_RETURN = 'return'
    TYPE_REFUND = 'refund'

    TRANSACTION_TYPES = [
        (TYPE_PURCHASE, 'Purchase'),
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_RETURN, 'Return'),
        (TYPE_REFUND, 'Refund'),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, null=True,
        related_name='vendor_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'vendor_transactions'
        verbose_name = _('Vendor transaction')
        verbose_name_plural = _('Vendor transactions')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.vendor.name} - {self.get_transaction_type_display()} - {self.amount}'
