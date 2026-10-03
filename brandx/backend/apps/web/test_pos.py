"""Web-level tests for the POS checkout, returns and cross-store isolation.

These replace the former API tests: the browser path (session auth, CSRF,
``/pos/checkout/`` JSON and the return form) is now the only path, so this is
where the business rules must be enforced.
"""
import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.authentication.models import User
from apps.inventory.models import StockMovement
from apps.products.models import Category, Product, ProductVariant
from apps.sales.models import Receipt, Sale, SaleReturn
from apps.stores.models import Store


class WebFlowTestBase(TestCase):
    """Shared helpers: two isolated stores, PIN login, catalog fixtures."""

    def setUp(self):
        self.store_a = Store.objects.create(name='Store A', code='AAA')
        self.store_b = Store.objects.create(name='Store B', code='BBB')
        self.owner_a = self._make_user('owner-a', 'owner', self.store_a, '1111')
        self.owner_b = self._make_user('owner-b', 'owner', self.store_b, '2222')

    def _make_user(self, username, role, store, pin):
        user = User(username=username, first_name=username.title(), role=role,
                    store=store, language='uz')
        user.set_unusable_password()
        user.set_pin(pin)
        user.save()
        return user

    def _login(self, code, pin):
        # The login page redirects already-authenticated users, so always start
        # from a clean session when switching accounts.
        self.client.logout()
        response = self.client.post(reverse('web:store-login', kwargs={'code': code}),
                                    {'pin': pin, 'store_code': code})
        self.assertEqual(response.status_code, 302)

    def _make_variant(self, store, barcode, stock=5, price='100', cost='60'):
        category = Category.objects.create(store=store, name=f'Cat-{barcode}')
        product = Product.objects.create(store=store, name=f'Item-{barcode}', barcode=barcode,
                                         category=category,
                                         base_selling_price=Decimal(price),
                                         base_cost_price=Decimal(cost))
        return ProductVariant.objects.create(store=store, product=product,
                                             sku=f'{barcode}-sku', barcode=barcode,
                                             stock_quantity=stock)

    def _checkout(self, variant, quantity=1, unit_price='100', **extra):
        payload = {'payment_method': 'cash', 'received_amount': '500',
                   'items': [{'product_variant_id': variant.pk, 'quantity': quantity,
                              'unit_price': unit_price}]}
        payload.update(extra)
        return self.client.post(reverse('web:pos-checkout'), data=json.dumps(payload),
                                content_type='application/json')


class PosCheckoutTests(WebFlowTestBase):
    def setUp(self):
        super().setUp()
        self._login('AAA', '1111')
        self.variant = self._make_variant(self.store_a, 'pos-variant', stock=5)

    def test_cash_checkout_creates_sale_with_change(self):
        response = self._checkout(self.variant, quantity=2, unit_price='100')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['change'], '300.00')  # 500 received - 200 total

        sale = Sale.objects.get(pk=payload['id'])
        self.assertEqual(sale.store, self.store_a)
        self.assertEqual(sale.total_amount, Decimal('200.00'))
        self.assertEqual(sale.cash_amount, Decimal('200.00'))
        self.assertEqual(sale.change_amount, Decimal('300.00'))
        self.assertEqual(sale.status, Sale.STATUS_COMPLETED)
        self.assertEqual(sale.items.count(), 1)
        self.assertEqual(sale.items.get().product_name, 'Item-pos-variant')
        self.assertTrue(Receipt.objects.filter(sale=sale).exists())

        # Stock went down through the audited movement trail.
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)
        movement = StockMovement.objects.get(product_variant=self.variant,
                                             movement_type=StockMovement.TYPE_SALE)
        self.assertEqual((movement.quantity_before, movement.quantity_after), (5, 3))

    def test_card_payment(self):
        response = self._checkout(self.variant, quantity=1, unit_price='100',
                                  payment_method='card', received_amount=0, card_amount='100')
        self.assertEqual(response.status_code, 200, response.content)
        sale = Sale.objects.get()
        self.assertEqual(sale.payment_method, Sale.PAYMENT_CARD)
        self.assertEqual(sale.card_amount, Decimal('100.00'))
        self.assertEqual(sale.cash_amount, Decimal('0'))
        self.assertEqual(sale.change_amount, Decimal('0'))

    def test_mixed_payment_exact_split(self):
        response = self._checkout(self.variant, quantity=1, unit_price='100',
                                  payment_method='mixed', received_amount='60', card_amount='40')
        self.assertEqual(response.status_code, 200, response.content)
        sale = Sale.objects.get()
        self.assertEqual(sale.cash_amount, Decimal('60.00'))
        self.assertEqual(sale.card_amount, Decimal('40.00'))
        self.assertEqual(sale.change_amount, Decimal('0'))

    def test_insufficient_stock_rejected_atomically(self):
        response = self._checkout(self.variant, quantity=10)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get('code'), 'insufficient_stock')
        self.assertFalse(Sale.objects.exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)  # untouched

    def test_cash_less_than_total_rejected(self):
        response = self._checkout(self.variant, quantity=1, unit_price='100',
                                  received_amount='10')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Sale.objects.exists())

    def test_discount_above_subtotal_rejected(self):
        response = self._checkout(self.variant, quantity=1, unit_price='100',
                                  discount_amount='999')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Sale.objects.exists())

    def test_empty_cart_rejected(self):
        response = self.client.post(reverse('web:pos-checkout'),
                                    data=json.dumps({'payment_method': 'cash', 'items': []}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_invalid_payload_rejected(self):
        response = self.client.post(reverse('web:pos-checkout'), data='not-json',
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_login_required(self):
        self.client.logout()
        response = self._checkout(self.variant, quantity=1)
        self.assertIn(response.status_code, (302, 403))


class SaleReturnTests(WebFlowTestBase):
    def setUp(self):
        super().setUp()
        self._login('AAA', '1111')
        self.variant = self._make_variant(self.store_a, 'ret-variant', stock=5)
        response = self._checkout(self.variant, quantity=2, unit_price='100')
        self.assertEqual(response.status_code, 200, response.content)
        self.sale = Sale.objects.get()
        self.sale_item = self.sale.items.get()

    def _post_return(self, quantity='2', **extra):
        data = {f'return_qty_{self.sale_item.pk}': quantity, 'reason': 'defect'}
        data.update(extra)
        return self.client.post(reverse('web:sale-return', kwargs={'pk': self.sale.pk}), data)

    def test_full_return_restores_stock_and_updates_status(self):
        response = self._post_return(quantity='2')
        self.assertEqual(response.status_code, 302, response.content)

        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_REFUNDED)
        return_doc = SaleReturn.objects.get(sale=self.sale)
        self.assertEqual(return_doc.total_amount, Decimal('200.00'))

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
        self.assertTrue(StockMovement.objects.filter(
            product_variant=self.variant, movement_type=StockMovement.TYPE_RETURN).exists())

    def test_partial_return_marks_partially_refunded(self):
        response = self._post_return(quantity='1')
        self.assertEqual(response.status_code, 302, response.content)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_PARTIALLY_REFUNDED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 4)

    def test_return_more_than_sold_rejected(self):
        response = self._post_return(quantity='5')
        self.assertEqual(response.status_code, 302)  # graceful redirect, never a 500
        self.assertFalse(SaleReturn.objects.exists())
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.STATUS_COMPLETED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)

    def test_cashier_cannot_return(self):
        cashier = self._make_user('ret-cashier', 'cashier', self.store_a, '3333')
        self.client.logout()
        self._login('AAA', '3333')
        self.assertEqual(self.client.session['_auth_user_id'], str(cashier.pk))
        response = self._post_return(quantity='1')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SaleReturn.objects.exists())

    def test_cannot_return_twice_the_same_line(self):
        self.assertEqual(self._post_return(quantity='2').status_code, 302)
        response = self._post_return(quantity='1')
        self.assertEqual(response.status_code, 302)  # rejected gracefully
        self.assertEqual(SaleReturn.objects.count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)


class ReceiptPdfTests(WebFlowTestBase):
    def setUp(self):
        super().setUp()
        self._login('AAA', '1111')
        self.variant = self._make_variant(self.store_a, 'pdf-variant', stock=5)
        response = self._checkout(self.variant, quantity=1, unit_price='100')
        self.sale = Sale.objects.get()

    def test_receipt_pdf_served(self):
        response = self.client.get(reverse('web:receipt-pdf', kwargs={'pk': self.sale.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content[:4], b'%PDF')


class CrossStoreIsolationTests(WebFlowTestBase):
    """The SSR pages must enforce the same store scoping the API used to."""

    def setUp(self):
        super().setUp()
        self.variant_b = self._make_variant(self.store_b, 'cross-variant', stock=3)

    def test_cannot_edit_other_store_product(self):
        self._login('AAA', '1111')
        response = self.client.get(reverse('web:product-edit',
                                           kwargs={'pk': self.variant_b.product.pk}))
        self.assertEqual(response.status_code, 404)

    def test_cannot_checkout_other_store_variant(self):
        self._login('AAA', '1111')
        response = self._checkout(self.variant_b, quantity=1)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Sale.objects.exists())

    def test_cannot_view_other_store_sale(self):
        self._login('BBB', '2222')
        response = self._checkout(self.variant_b, quantity=1, unit_price='100')
        sale_b = Sale.objects.get()
        self.assertEqual(sale_b.store, self.store_b)

        self._login('AAA', '1111')
        response = self.client.get(reverse('web:sale-detail', kwargs={'pk': sale_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_cannot_view_other_store_receipt(self):
        self._login('BBB', '2222')
        response = self._checkout(self.variant_b, quantity=1, unit_price='100')
        self.assertEqual(response.status_code, 200)
        receipt_b = Receipt.objects.get()

        self._login('AAA', '1111')
        response = self.client.get(reverse('web:receipt-detail', kwargs={'pk': receipt_b.pk}))
        self.assertEqual(response.status_code, 404)
