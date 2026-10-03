"""Web-level report export tests: role gating, store scoping and file formats."""
from django.test import TestCase
from django.urls import reverse

from apps.authentication.models import User
from apps.products.models import Category, Product, ProductVariant
from apps.stores.models import Store

CSV_MIME = 'text/csv; charset=utf-8'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class ReportExportTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.create(name='Export A', code='EXPA')
        self.store_b = Store.objects.create(name='Export B', code='EXPB')
        self.owner = self._make_user('expa-owner', 'owner', self.store_a, '1111')
        self.manager = self._make_user('expa-manager', 'manager', self.store_a, '2222')
        self.cashier = self._make_user('expa-cashier', 'cashier', self.store_a, '3333')
        self.owner_b = self._make_user('expb-owner', 'owner', self.store_b, '4444')

        self.variant_a = self._variant(self.store_a, 'exp-variant-a')
        self.variant_b = self._variant(self.store_b, 'exp-variant-b')

        self._login('1111')
        self._checkout(self.variant_a)
        self.client.logout()
        self._login('4444', code='EXPB')
        self._checkout(self.variant_b)
        self.client.logout()
        self._login('1111')  # back to the store-A owner

    # ── helpers ──────────────────────────────────────────────────────
    def _make_user(self, username, role, store, pin):
        user = User(username=username, first_name=username.title(), role=role,
                    store=store, language='uz')
        user.set_unusable_password()
        user.set_pin(pin)
        user.save()
        return user

    def _variant(self, store, barcode):
        category = Category.objects.create(store=store, name=f'Cat-{barcode}')
        product = Product.objects.create(store=store, name=f'Item-{barcode}', barcode=barcode,
                                         category=category, base_selling_price=100,
                                         base_cost_price=60)
        return ProductVariant.objects.create(store=store, product=product, sku=f'{barcode}-sku',
                                             barcode=barcode, stock_quantity=5)

    def _login(self, pin, code='EXPA'):
        response = self.client.post(reverse('web:store-login', kwargs={'code': code}),
                                    {'pin': pin, 'store_code': code})
        self.assertEqual(response.status_code, 302)

    def _checkout(self, variant):
        from apps.web.views.sales import _create_sale
        request = self.client
        # Reuse the web checkout endpoint so the fixtures match real usage.
        import json
        response = self.client.post(reverse('web:pos-checkout'), data=json.dumps({
            'payment_method': 'cash', 'received_amount': '500',
            'items': [{'product_variant_id': variant.pk, 'quantity': 1, 'unit_price': '100'}]}),
            content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def _export(self, kind, **params):
        url = reverse('web:report-export', kwargs={'kind': kind})
        return self.client.get(url, params or None)

    # ── tests ────────────────────────────────────────────────────────
    def test_sales_csv_is_scoped_to_own_store(self):
        response = self._export('sales', fmt='csv', period='all')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertIn('attachment', response['Content-Disposition'])
        text = response.content.decode('utf-8-sig')
        self.assertIn('Item-exp-variant-a', text)      # own sale is present
        self.assertNotIn('Item-exp-variant-b', text)   # other store's sale is not

    def test_sales_xlsx_is_the_default_format(self):
        response = self._export('sales', period='all')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], XLSX_MIME)
        self.assertEqual(response.content[:2], b'PK')  # zip container of .xlsx

    def test_stock_export_scoped(self):
        response = self._export('stock', fmt='csv')
        self.assertEqual(response.status_code, 200)
        text = response.content.decode('utf-8-sig')
        self.assertIn('Item-exp-variant-a', text)
        self.assertNotIn('Item-exp-variant-b', text)

    def test_receipts_export_is_owner_only(self):
        response = self._export('receipts', fmt='csv')
        self.assertEqual(response.status_code, 200)

        self.client.logout()
        self._login('2222')  # manager
        response = self._export('receipts', fmt='csv')
        self.assertEqual(response.status_code, 302)  # redirected, no file leaked

    def test_financial_summary_is_owner_only(self):
        response = self._export('financial-summary', fmt='csv')
        self.assertEqual(response.status_code, 200)

        self.client.logout()
        self._login('3333')  # cashier
        response = self._export('financial-summary', fmt='csv')
        self.assertEqual(response.status_code, 302)

    def test_unknown_kind_is_404(self):
        response = self._export('does-not-exist')
        self.assertEqual(response.status_code, 404)
