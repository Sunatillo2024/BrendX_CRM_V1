"""Smoke tests for the server-rendered UI: every page must render."""
from django.test import TestCase
from django.urls import reverse

from apps.authentication.models import User
from apps.products.models import Category, Product, ProductVariant
from apps.stores.models import Store


class WebPageTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name='Test Store', code='TST')
        self.owner = User(username='tst-owner', first_name='Owner', role='owner',
                          store=self.store, language='uz')
        self.owner.set_unusable_password()
        self.owner.set_pin('1234')
        self.owner.save()

        self.category = Category.objects.create(store=self.store, name='Shirts')
        self.product = Product.objects.create(store=self.store, name='Shirt', barcode='2000000000017',
                                              category=self.category, base_selling_price=100,
                                              base_cost_price=60)
        ProductVariant.objects.create(store=self.store, product=self.product, sku='SHIRT-1',
                                      barcode='2000000000024', stock_quantity=5, low_stock_threshold=2)

    def login(self):
        response = self.client.post(reverse('web:store-login', kwargs={'code': 'TST'}),
                                    {'pin': '1234', 'store_code': 'TST'})
        self.assertEqual(response.status_code, 302)

    def test_login_page_renders(self):
        # Without a store code the page asks for the store first.
        response = self.client.get(reverse('web:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'store_code')
        # With a store code it shows the PIN pad.
        response = self.client.get(reverse('web:store-login', kwargs={'code': 'TST'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PIN')

    def test_login_with_pin(self):
        response = self.client.post(reverse('web:store-login', kwargs={'code': 'TST'}),
                                    {'pin': '1234', 'store_code': 'TST'})
        self.assertEqual(response.status_code, 302)

    def test_page_can_be_rendered(self):
        self.login()
        names = ['web:dashboard', 'web:pos', 'web:product-list', 'web:category-list',
                 'web:stock', 'web:receipts', 'web:sales-list', 'web:finance',
                 'web:reports', 'web:employees', 'web:settings']
        for name in names:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, f'{name} failed')

    def test_product_form_renders(self):
        self.login()
        self.assertEqual(self.client.get(reverse('web:product-create')).status_code, 200)
        self.assertEqual(self.client.get(
            reverse('web:product-edit', kwargs={'pk': self.product.pk})).status_code, 200)

    def test_product_create_via_form(self):
        """The exact payload the browser sends (no variant threshold column)."""
        self.login()
        response = self.client.post(reverse('web:product-create'), {
            'name': 'New Shirt', 'barcode': '3000000000015',
            'base_selling_price': '150', 'base_cost_price': '90',
            'low_stock_threshold': '2', 'is_active': 'on',
            'variants-TOTAL_FORMS': '1', 'variants-INITIAL_FORMS': '0',
            'variants-MIN_NUM_FORMS': '0', 'variants-MAX_NUM_FORMS': '1000',
            'variants-0-stock_quantity': '7', 'variants-0-is_active': 'on',
        })
        self.assertEqual(response.status_code, 302, response.content)
        product = Product.objects.get(barcode='3000000000015')
        variant = product.variants.get()
        self.assertEqual(variant.stock_quantity, 7)
        self.assertEqual(variant.low_stock_threshold, 5)  # model default applied
        self.assertEqual(product.base_cost_price, 90)

    def test_manager_can_create_product_without_cost(self):
        """The cost column is owner-only; the form must still accept managers."""
        manager = User(username='tst-manager', first_name='M', role='manager',
                       store=self.store, language='uz')
        manager.set_unusable_password()
        manager.set_pin('5555')
        manager.save()
        self.client.logout()
        self.client.post(reverse('web:store-login', kwargs={'code': 'TST'}),
                         {'pin': '5555', 'store_code': 'TST'})
        response = self.client.post(reverse('web:product-create'), {
            'name': 'Manager Item', 'base_selling_price': '100', 'is_active': 'on',
            'variants-TOTAL_FORMS': '1', 'variants-INITIAL_FORMS': '0',
            'variants-MIN_NUM_FORMS': '0', 'variants-MAX_NUM_FORMS': '1000',
            'variants-0-stock_quantity': '4', 'variants-0-is_active': 'on',
        })
        self.assertEqual(response.status_code, 302, response.content)
        product = Product.objects.get(name='Manager Item')
        self.assertEqual(product.base_cost_price, 0)

    def test_pos_search(self):
        self.login()
        response = self.client.get(reverse('web:pos-search'), {'q': 'Shirt'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.json())
        self.assertEqual(len(response.json()['results']), 1)

    def test_category_create(self):
        self.login()
        response = self.client.post(reverse('web:category-save'),
                                    {'name': 'Pants', 'description': 'x', 'is_active': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Category.objects.filter(store=self.store, name='Pants').exists())

    def test_employee_create_and_pin(self):
        self.login()
        response = self.client.post(reverse('web:employee-save'), {
            'first_name': 'Cashier', 'last_name': 'One', 'username': 'tst-cashier',
            'role': 'cashier', 'language': 'uz', 'pin': '9876', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        cashier = User.objects.get(username='tst-cashier')
        self.assertTrue(cashier.check_pin('9876'))

    def test_platform_admin_pages(self):
        admin = User(username='platform', role='platform_admin', store=None, language='uz')
        admin.set_unusable_password()
        admin.set_pin('4321')
        admin.save()
        response = self.client.post(reverse('web:platform-login'), {'pin': '4321'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse('web:platform')).status_code, 200)
