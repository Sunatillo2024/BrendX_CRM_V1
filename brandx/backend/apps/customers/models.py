"""Customers App Models - simple customer registry (no credit / installments)"""
from django.db import models
from apps.stores.models import StoreOwned
from django.utils.translation import gettext_lazy as _


class Customer(StoreOwned):
    """
    Simple customer record.

    Kept minimal on purpose: a clothes shop needs a name and a phone on the
    receipt, nothing more. Credit / installment logic was intentionally removed.
    """
    name = models.CharField(max_length=200, db_index=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customers'
        verbose_name = _('Customer')
        verbose_name_plural = _('Customers')
        ordering = ['name']

    def __str__(self):
        return self.name
