from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LegacyBackfillTests(TransactionTestCase):
    def test_legacy_rows_and_cashier_relationship_survive(self):
        executor=MigrationExecutor(connection)
        before=[('stores','0001_initial'),('authentication','0004_user_store_alter_user_role_and_more'),
            ('products','0003_remove_product_products_name_d2210c_idx_and_more'),
            ('customers','0003_customer_store'),('vendors','0003_vendor_store'),
            ('finance','0002_remove_financeentry_finance_ent_entry_t_615e1e_idx_and_more'),
            ('sales','0003_remove_sale_sales_created_7cca36_idx_sale_store_and_more'),
            ('inventory','0003_stockreceipt_store_alter_stockreceipt_number_and_more'),
            ('audit','0004_auditlog_store')]
        executor.migrate(before)
        historical=executor.loader.project_state(before).apps
        User=historical.get_model('authentication','User')
        Product=historical.get_model('products','Product')
        Sale=historical.get_model('sales','Sale')
        user=User.objects.create(username='admin',role='owner',pin_hash='preserved-hash')
        employee=User.objects.create(username='legacy-cashier',role='cashier',is_staff=True)
        product=Product.objects.create(name='Legacy product',barcode='legacy',base_selling_price=100)
        sale=Sale.objects.create(cashier=user,number=1,subtotal=100,total_amount=100)
        ids=user.pk,employee.pk,product.pk,sale.pk
        try:
            executor=MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Store
            from apps.authentication.models import User as CurrentUser
            from apps.products.models import Product as CurrentProduct
            from apps.sales.models import Sale as CurrentSale
            store=Store.objects.get(code='BRANDX')
            admin=CurrentUser.objects.get(pk=ids[0])
            self.assertEqual(admin.role,'platform_admin')
            self.assertIsNone(admin.store_id)
            self.assertEqual(admin.pin_hash,'preserved-hash')
            cashier=CurrentUser.objects.get(pk=ids[1])
            self.assertEqual(cashier.store_id,store.pk)
            self.assertFalse(cashier.is_staff)
            self.assertEqual(CurrentProduct.objects.get(pk=ids[2]).store_id,store.pk)
            restored=CurrentSale.objects.get(pk=ids[3])
            self.assertEqual(restored.cashier_id,admin.pk)
            self.assertEqual(restored.store_id,store.pk)
        finally:
            executor=MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
