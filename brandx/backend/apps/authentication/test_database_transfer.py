import copy
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.management.base import CommandError
from django.test import TestCase

from apps.common.database_transfer import (
    digest, export_archive, import_archive, manifest, snapshot,
)
from apps.products.models import Product, ProductVariant
from apps.sales.models import Receipt, Sale, SaleItem

from .models import User
from apps.stores.models import Store


class DatabaseTransferTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name='Transfer', code='TRANSFER')
        self.user = User.objects.create_user(store=self.store, username='transfer-owner', role='owner')
        self.user.set_pin('0808')
        self.user.save()
        group = Group.objects.create(name='Transfer operators')
        permission = Permission.objects.get(codename='view_product', content_type__app_label='products')
        group.permissions.add(permission)
        self.user.groups.add(group)
        self.user.user_permissions.add(permission)
        product = Product.objects.create(store=self.store, 
            name='Футболка', barcode='product-transfer',
            base_cost_price=Decimal('15.25'), base_selling_price=Decimal('23.50'),
        )
        self.variant = ProductVariant.objects.create(store=self.store, 
            product=product, sku='transfer-sku', barcode='variant-transfer', stock_quantity=2,
        )
        self.sale = Sale.objects.create(store=self.store, 
            number=1, cashier=self.user, subtotal=Decimal('23.50'),
            total_amount=Decimal('23.50'), cash_amount=Decimal('23.50'),
        )
        SaleItem.objects.create(
            sale=self.sale, product_variant=self.variant, product_name=product.name,
            quantity=1, unit_price=Decimal('23.50'), unit_cost=Decimal('15.25'),
        )
        Receipt.objects.create(sale=self.sale, receipt_number='000001')

    def clear_source(self):
        Receipt.objects.all().delete()
        SaleItem.objects.all().delete()
        Sale.objects.all().delete()
        ProductVariant.objects.all().delete()
        Product.objects.all().delete()
        User.objects.all().delete()
        Group.objects.all().delete()
        Store.objects.all().delete()

    def test_exact_roundtrip_preserves_ids_hashes_costs_and_relationships(self):
        archive = export_archive()
        original_pin_hash = self.user.pin_hash
        user_id, sale_id = self.user.pk, self.sale.pk
        self.clear_source()
        import_archive(archive)
        self.assertEqual(digest(snapshot()), archive['sha256'])
        self.assertEqual(manifest(snapshot()), archive['manifest'])
        self.assertEqual(User.objects.get(pk=user_id).pin_hash, original_pin_hash)
        restored_user = User.objects.get(pk=user_id)
        self.assertTrue(restored_user.check_pin('0808'))
        self.assertEqual(restored_user.groups.get().name, 'Transfer operators')
        self.assertEqual(restored_user.user_permissions.get().codename, 'view_product')
        self.assertEqual(restored_user.groups.get().permissions.get().codename, 'view_product')
        sale = Sale.objects.get(pk=sale_id)
        self.assertEqual(sale.cashier_id, user_id)
        self.assertEqual(sale.items.get().unit_cost, Decimal('15.25'))
        self.assertEqual(sale.items.get().product_variant_id, self.variant.pk)
        self.assertEqual(sale.receipt.receipt_number, '000001')
        # Sequence reset must leave new writes able to allocate fresh IDs.
        self.assertGreater(User.objects.create_user(store_id=self.store.pk, username='after-import').pk, user_id)

    def test_nonempty_target_is_never_overwritten(self):
        archive = export_archive()
        with self.assertRaisesMessage(CommandError, 'not empty'):
            import_archive(archive)
        self.assertEqual(digest(snapshot()), archive['sha256'])

    def test_tampered_archive_is_rejected_without_writes(self):
        archive = export_archive()
        archive['records'][0]['fields']['language'] = 'tampered'
        with self.assertRaisesMessage(CommandError, 'checksum'):
            import_archive(archive)
        self.assertEqual(Sale.objects.count(), 1)

    def test_unknown_models_are_rejected(self):
        archive = export_archive()
        archive['records'][0]['model'] = 'other.secret'
        archive['sha256'] = digest(archive['records'])
        with self.assertRaisesMessage(CommandError, 'Unknown model'):
            import_archive(archive)

    def test_bad_relationship_rolls_back_all_imported_records(self):
        archive = copy.deepcopy(export_archive())
        sale_row = next(row for row in archive['records'] if row['model'] == 'sales.sale')
        sale_row['fields']['cashier'] = ['missing-employee']
        archive['sha256'] = digest(archive['records'])
        archive['manifest'] = manifest(archive['records'])
        self.clear_source()
        with self.assertRaises(Exception):
            import_archive(archive)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(Product.objects.count(), 0)
