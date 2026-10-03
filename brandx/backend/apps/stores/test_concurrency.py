"""PostgreSQL row-lock concurrency checks for the POS checkout path.

These tests exercise the exact code the browser uses —
``apps.web.views.sales._create_sale`` and ``apps.sales.returns.process_return`` —
without the HTTP layer, because all checkout business rules live there.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import RequestFactory, TransactionTestCase

from apps.authentication.models import User
from apps.inventory.services import InsufficientStock
from apps.products.models import Product, ProductVariant
from apps.sales.models import Sale
from apps.sales.returns import process_return
from apps.web.views.sales import _create_sale

from .models import Store


@skipUnless(connection.vendor == 'postgresql', 'Requires actual PostgreSQL row locks')
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.store = Store.objects.create(name='Concurrent', code='CONCURRENT')
        self.user = User.objects.create_user(store=self.store, username='concurrent', role='owner')
        product = Product.objects.create(store=self.store, name='Last item', barcode='con-product',
            base_selling_price=100, base_cost_price=40)
        self.variant = ProductVariant.objects.create(store=self.store, product=product,
            barcode='con-variant', sku='con-sku', stock_quantity=1)

    def checkout(self, variant_id):
        close_old_connections()
        try:
            request = self.factory.post('/pos/checkout/')
            request.user = User.objects.get(pk=self.user.pk)
            data = {'payment_method': 'cash', 'received_amount': '100',
                    'items': [{'product_variant_id': variant_id, 'quantity': 1, 'unit_price': '100'}]}
            return _create_sale(request, self.store, data)
        except Exception as exc:  # return the failure type instead of raising in a worker
            return type(exc)
        finally:
            close_old_connections()

    def test_two_checkouts_cannot_oversell_last_unit(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(self.checkout, [self.variant.pk, self.variant.pk]))
        sales = [o for o in outcomes if isinstance(o, Sale)]
        failures = [o for o in outcomes if o is InsufficientStock]
        self.assertEqual(len(sales), 1)
        self.assertEqual(len(failures), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 0)
        self.assertEqual(Sale.objects.count(), 1)

    def test_empty_store_parallel_numbering_is_unique(self):
        self.variant.stock_quantity = 2
        self.variant.save()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(self.checkout, [self.variant.pk, self.variant.pk]))
        self.assertTrue(all(isinstance(o, Sale) for o in outcomes), outcomes)
        self.assertEqual(set(Sale.objects.values_list('number', flat=True)), {1, 2})

    def test_parallel_returns_cannot_refund_twice(self):
        sale = self.checkout(self.variant.pk)
        self.assertIsInstance(sale, Sale)
        item_id = sale.items.get().pk

        def refund(_):
            close_old_connections()
            try:
                request = self.factory.post('/pos/checkout/')
                request.user = User.objects.get(pk=self.user.pk)
                return process_return(sale, {'items': [{'sale_item': item_id, 'quantity': 1}]}, request.user)
            except ValidationError:
                return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(refund, [0, 1]))
        documents = [o for o in outcomes if not isinstance(o, str)]
        self.assertEqual(len(documents), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 1)
        self.assertEqual(sale.returns.get().total_amount, Decimal('100'))
