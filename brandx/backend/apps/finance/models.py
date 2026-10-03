"""Finance Models - Income / Expense entries (Кирим / Чиқим)"""
from django.db import models
from apps.stores.models import StoreOwned
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class FinanceEntry(StoreOwned):
    """
    A single income or expense entry.

    Expenses: rent, electricity, delivery, salary, packaging, repair, other.
    Income: non-sale income (e.g. rent from a sub-tenant, scrap sales).
    """
    TYPE_INCOME = 'income'
    TYPE_EXPENSE = 'expense'

    TYPE_CHOICES = [
        (TYPE_INCOME, 'Income'),
        (TYPE_EXPENSE, 'Expense'),
    ]

    entry_type = models.CharField(max_length=10, choices=TYPE_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    category = models.CharField(max_length=100, blank=True, db_index=True)
    comment = models.TextField(blank=True)
    entry_date = models.DateField(default=timezone.localdate, db_index=True)
    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, null=True, related_name='finance_entries'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'finance_entries'
        ordering = ['-entry_date', '-created_at']
        verbose_name = _('Income / Expense')
        verbose_name_plural = _('Income / Expenses')
        indexes = [models.Index(fields=['store', 'entry_type', '-entry_date'])]

    def __str__(self):
        return f'{self.get_entry_type_display()} {self.amount}'
