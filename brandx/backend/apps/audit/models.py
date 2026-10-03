"""Audit log - records WHO did WHAT and WHEN. Never stores secrets/PINs."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditLog(models.Model):
    """Append-only trail of important actions."""

    ACTION_LOGIN = 'login'
    ACTION_LOGIN_FAILED = 'login_failed'
    ACTION_LOGOUT = 'logout'
    ACTION_USER_CREATED = 'user_created'
    ACTION_USER_UPDATED = 'user_updated'
    ACTION_USER_DEACTIVATED = 'user_deactivated'
    ACTION_PIN_CHANGED = 'pin_changed'
    ACTION_PRODUCT_CREATED = 'product_created'
    ACTION_PRODUCT_UPDATED = 'product_updated'
    ACTION_PRODUCT_DELETED = 'product_deleted'
    ACTION_PRICE_CHANGED = 'price_changed'
    ACTION_CATEGORY_CHANGED = 'category_changed'
    ACTION_STOCK_RECEIPT = 'stock_receipt'
    ACTION_STOCK_ADJUSTED = 'stock_adjusted'
    ACTION_INVENTORY_COUNT = 'inventory_count'
    ACTION_SALE_CREATED = 'sale_created'
    ACTION_SALE_RETURNED = 'sale_returned'
    ACTION_EXPENSE_CREATED = 'expense_created'
    ACTION_INCOME_CREATED = 'income_created'
    ACTION_FINANCE_DELETED = 'finance_deleted'
    ACTION_SETTINGS_CHANGED = 'settings_changed'

    ACTION_CHOICES = [
        (ACTION_LOGIN, 'Login'),
        (ACTION_LOGIN_FAILED, 'Failed login'),
        (ACTION_LOGOUT, 'Logout'),
        (ACTION_USER_CREATED, 'User created'),
        (ACTION_USER_UPDATED, 'User updated'),
        (ACTION_USER_DEACTIVATED, 'User deactivated'),
        (ACTION_PIN_CHANGED, 'PIN changed'),
        (ACTION_PRODUCT_CREATED, 'Product created'),
        (ACTION_PRODUCT_UPDATED, 'Product updated'),
        (ACTION_PRODUCT_DELETED, 'Product deleted'),
        (ACTION_PRICE_CHANGED, 'Price changed'),
        (ACTION_CATEGORY_CHANGED, 'Category changed'),
        (ACTION_STOCK_RECEIPT, 'Stock receipt'),
        (ACTION_STOCK_ADJUSTED, 'Stock adjusted'),
        (ACTION_INVENTORY_COUNT, 'Inventory count'),
        (ACTION_SALE_CREATED, 'Sale created'),
        (ACTION_SALE_RETURNED, 'Sale returned'),
        (ACTION_EXPENSE_CREATED, 'Expense created'),
        (ACTION_INCOME_CREATED, 'Income created'),
        (ACTION_FINANCE_DELETED, 'Finance entry deleted'),
        (ACTION_SETTINGS_CHANGED, 'Settings changed'),
    ]

    store = models.ForeignKey('stores.Store', on_delete=models.PROTECT, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs'
    )
    # Denormalised so the trail survives user deletion
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    entity = models.CharField(max_length=50, blank=True)
    entity_id = models.CharField(max_length=50, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_logs'
        verbose_name = _('Audit log')
        verbose_name_plural = _('Audit logs')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.username or "-"} {self.action}'
