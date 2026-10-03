"""Inventory service tests: goods receipts, adjustments, the movement trail
and store-tenancy enforcement.

The services are the single write path for stock, so these rules protect the
web UI as well as any future client.
"""
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.authentication.models import User
from apps.inventory import services as inventory_services
from apps.inventory.models import StockMovement, StockReceipt
from apps.products.models import Category, Product, ProductVariant
from apps.stores.models import Store


class InventoryServiceBase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name='Inv Store', code='INV')
        self.owner = self._make_user('inv-owner', self.store, '1234')
        category = Category.objects.create(store=self.store, name='Cat')
        product = Product.objects.create(store=self.store, name='Item', barcode='inv-barcode',
                                         category=category, base_selling_price=Decimal('100'),
                                         base_cost_price=Decimal('60'))
        self.variant = ProductVariant.objects.create(store=self.store, product=product,
                                                     sku='inv-sku', barcode='inv-barcode-v',
                                                     stock_quantity=0)

    def _make_user(self, username, store, pin):
        user = User(username=username, first_name=username.title(), role='owner',
                    store=store, language='uz')
        user.set_unusable_password()
        user.set_pin(pin)
        user.save()
        return user


class ReceiveStockTests(InventoryServiceBase):
    def test_receipt_increases_stock_and_records_trail(self):
        receipt = inventory_services.receive_stock(
            items=[{'product_variant': self.variant, 'quantity': 10, 'cost_price': Decimal('40')}],
            user=self.owner)

        self.assertIsInstance(receipt, StockReceipt)
        self.assertEqual(receipt.store, self.store)
        self.assertEqual(receipt.items.count(), 1)
        self.assertEqual(receipt.total_quantity, 10)
        self.assertEqual(receipt.total_cost, Decimal('400'))

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)
        # Latest purchase price becomes the variant cost (profit reports).
        self.assertEqual(self.variant.cost_price, Decimal('40'))

        movement = StockMovement.objects.get(product_variant=self.variant,
                                             movement_type=StockMovement.TYPE_PURCHASE)
        self.assertEqual((movement.quantity_before, movement.quantity_change,
                          movement.quantity_after), (0, 10, 10))
        self.assertEqual(movement.receipt_id, receipt.pk)
        self.assertEqual(movement.created_by, self.owner)

    def test_second_receipt_updates_cost_price(self):
        inventory_services.receive_stock(
            items=[{'product_variant': self.variant, 'quantity': 5, 'cost_price': '40'}],
            user=self.owner)
        inventory_services.receive_stock(
            items=[{'product_variant': self.variant, 'quantity': 5, 'cost_price': '50'}],
            user=self.owner)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.cost_price, Decimal('50'))
        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(StockReceipt.objects.count(), 2)

    def test_receipt_requires_store_user(self):
        with self.assertRaises(PermissionDenied):
            inventory_services.receive_stock(
                items=[{'product_variant': self.variant, 'quantity': 1, 'cost_price': '1'}],
                user=None)


class ChangeStockTests(InventoryServiceBase):
    def setUp(self):
        super().setUp()
        inventory_services.receive_stock(
            items=[{'product_variant': self.variant, 'quantity': 5, 'cost_price': '40'}],
            user=self.owner)

    def test_adjustment_records_readable_trail(self):
        movement = inventory_services.change_stock(
            self.variant, -2, StockMovement.TYPE_ADJUSTMENT,
            user=self.owner, reason='damage')

        self.assertEqual((movement.quantity_before, movement.quantity_change,
                          movement.quantity_after), (5, -2, 3))
        self.assertEqual(movement.reason, 'damage')
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)

    def test_cannot_go_below_zero(self):
        with self.assertRaises(inventory_services.InsufficientStock):
            inventory_services.change_stock(self.variant, -99, StockMovement.TYPE_ADJUSTMENT,
                                            user=self.owner)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)  # untouched

    def test_cross_store_user_denied(self):
        other_store = Store.objects.create(name='Other', code='OTHER')
        intruder = self._make_user('intruder', other_store, '4321')
        with self.assertRaises(PermissionDenied):
            inventory_services.change_stock(self.variant, 1, StockMovement.TYPE_ADJUSTMENT,
                                            user=intruder)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)


class WebStockAdjustTests(InventoryServiceBase):
    """The /stock/adjust/ page must go through the same guarded services."""

    def setUp(self):
        super().setUp()
        response = self.client.post(reverse('web:store-login', kwargs={'code': 'INV'}),
                                    {'pin': '1234', 'store_code': 'INV'})
        self.assertEqual(response.status_code, 302)

    def test_adjust_via_web_form(self):
        response = self.client.post(reverse('web:stock-adjust'), {
            'variant_id': self.variant.pk, 'mode': 'delta',
            'quantity': '3', 'reason': 'correction', 'notes': ''})
        self.assertEqual(response.status_code, 302)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)
        self.assertTrue(StockMovement.objects.filter(
            product_variant=self.variant, movement_type=StockMovement.TYPE_ADJUSTMENT).exists())

    def test_adjust_below_zero_rejected_via_web(self):
        response = self.client.post(reverse('web:stock-adjust'), {
            'variant_id': self.variant.pk, 'mode': 'delta', 'quantity': '-1'})
        self.assertEqual(response.status_code, 302)  # graceful redirect with error
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 0)
        self.assertFalse(StockMovement.objects.filter(
            product_variant=self.variant, movement_type=StockMovement.TYPE_ADJUSTMENT).exists())
