"""
Inventory services.

Every stock change in the system goes through ``change_stock`` so that
ProductVariant.stock_quantity and the StockMovement trail can never drift apart.
All operations are transaction-safe and lock the variant row while updating.
"""
from django.db import transaction

from apps.products.models import ProductVariant

from .models import StockMovement, StockReceipt, StockReceiptItem


class InsufficientStock(Exception):
    """Raised when a change would push stock below zero."""

    def __init__(self, variant, available, requested):
        self.variant = variant
        self.available = available
        self.requested = requested
        super().__init__(
            f'Insufficient stock for {variant}. Available: {available}, requested: {requested}.'
        )


@transaction.atomic
def change_stock(variant, delta, movement_type, *, user=None, reason='', unit_cost=None,
                 receipt=None, sale=None, reference='', notes='', allow_negative=False):
    """
    Apply a signed stock change and record a StockMovement.

    ``delta`` is positive for stock in, negative for stock out.
    Returns the created StockMovement.
    """
    if user is not None:
        from apps.common.tenancy import active_store
        store = active_store(user)
        if variant.store_id != store.pk or (sale and sale.store_id != store.pk) or (receipt and receipt.store_id != store.pk):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('Cross-store stock operation denied.')
    locked = ProductVariant.objects.select_for_update().get(pk=variant.pk)
    before = locked.stock_quantity
    after = before + int(delta)

    if after < 0 and not allow_negative:
        raise InsufficientStock(locked, before, abs(int(delta)))

    if after != before:
        locked.stock_quantity = after
        locked.save(update_fields=['stock_quantity', 'updated_at'])

    movement = StockMovement.objects.create(
        product_variant=locked,
        movement_type=movement_type,
        quantity_before=before,
        quantity_change=int(delta),
        quantity_after=after,
        unit_cost=unit_cost,
        reason=reason or '',
        reference=reference or '',
        receipt=receipt,
        sale=sale,
        notes=notes or '',
        created_by=user if getattr(user, 'pk', None) else None,
    )
    # Keep the in-memory instance consistent for the caller
    variant.stock_quantity = after
    return movement


@transaction.atomic
def receive_stock(*, items, user=None, vendor=None, receipt_date=None, notes=''):
    """
    Create a goods receipt ("Поступление") and push the stock in.

    ``items`` is a list of dicts: {'product_variant': <id|instance>, 'quantity': int,
    'cost_price': Decimal}.
    """
    from apps.common.tenancy import active_store
    store = active_store(user)
    if vendor and vendor.store_id != store.pk:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Cross-store vendor denied.')
    receipt = StockReceipt(store=store, number=store.next_number('receipt'), vendor=vendor, notes=notes or '')
    if receipt_date:
        receipt.receipt_date = receipt_date
    receipt.created_by = user if getattr(user, 'pk', None) else None
    receipt.save()

    for row in items:
        variant = row['product_variant']
        if not isinstance(variant, ProductVariant):
            variant = ProductVariant.objects.get(pk=variant, store=store)
        quantity = int(row['quantity'])
        cost_price = row.get('cost_price') or 0

        StockReceiptItem.objects.create(
            receipt=receipt, product_variant=variant, quantity=quantity, cost_price=cost_price
        )

        change_stock(
            variant, quantity, StockMovement.TYPE_PURCHASE,
            user=user, unit_cost=cost_price, receipt=receipt,
            reference=f'#{receipt.number}', notes=notes or '',
        )

        # Latest purchase price becomes the variant cost (used for profit reports)
        if cost_price:
            variant.cost_price = cost_price
            variant.save(update_fields=['cost_price', 'updated_at'])

    receipt.recalculate_totals()
    return receipt


def sell_stock(variant, quantity, sale, user=None):
    """Deduct stock for a sale line."""
    return change_stock(
        variant, -abs(int(quantity)), StockMovement.TYPE_SALE,
        user=user, sale=sale, reference=sale.sale_number,
    )


def return_stock(variant, quantity, sale=None, user=None, reason='return', notes=''):
    """Put returned goods back on the shelf."""
    return change_stock(
        variant, abs(int(quantity)), StockMovement.TYPE_RETURN,
        user=user, sale=sale, reason=reason, notes=notes,
        reference=sale.sale_number if sale else '',
    )


def set_counted_stock(variant, counted_quantity, user=None, reason='inventory', notes='',
                      movement_type=StockMovement.TYPE_INVENTORY):
    """Inventory count: set stock to the physically counted quantity."""
    with transaction.atomic():
        variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)
        delta = int(counted_quantity) - variant.stock_quantity
        return change_stock(
            variant, delta, movement_type, user=user, reason=reason, notes=notes,
        )
