from decimal import Decimal
from django.db import migrations

ROOTS = [('products', n) for n in ('Category', 'Color', 'Size', 'Product', 'ProductVariant')] + [
    ('customers', 'Customer'), ('vendors', 'Vendor'), ('finance', 'FinanceEntry'),
    ('sales', 'Sale'), ('inventory', 'StockReceipt'),
]


def forwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    Store = apps.get_model('stores', 'Store')
    User = apps.get_model('authentication', 'User')
    has_legacy = User.objects.using(alias).exists() or any(
        apps.get_model(a, m).objects.using(alias).exists() for a, m in ROOTS)
    if not has_legacy:
        return
    store, _ = Store.objects.using(alias).get_or_create(code='BRANDX', defaults={'name': 'BrandX'})
    for app, name in ROOTS:
        apps.get_model(app, name).objects.using(alias).filter(store__isnull=True).update(store=store)
    User.objects.using(alias).filter(store__isnull=True).exclude(role='platform_admin').update(
        store=store, is_staff=False, is_superuser=False)
    User.objects.using(alias).filter(username='admin').update(
        role='platform_admin', store=None, is_staff=True, is_superuser=True)
    Audit = apps.get_model('audit', 'AuditLog')
    # Old single-store events retain that store even if their actor is now global.
    Audit.objects.using(alias).filter(store__isnull=True).update(store=store)
    Return = apps.get_model('sales', 'SaleReturn')
    for ret in Return.objects.using(alias).select_related('sale'):
        total = ret.sale.total_amount
        cash = ((ret.total_amount * ret.sale.cash_amount / total).quantize(Decimal('0.01'))
                if total else Decimal('0'))
        ret.cash_amount = cash
        ret.card_amount = ret.total_amount - cash
        ret.save(using=alias, update_fields=['cash_amount', 'card_amount'])


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0001_initial'),
        ('authentication', '0004_user_store_alter_user_role_and_more'),
        ('products', '0003_remove_product_products_name_d2210c_idx_and_more'),
        ('customers', '0003_customer_store'), ('vendors', '0003_vendor_store'),
        ('finance', '0002_remove_financeentry_finance_ent_entry_t_615e1e_idx_and_more'),
        ('sales', '0003_remove_sale_sales_created_7cca36_idx_sale_store_and_more'),
        ('inventory', '0003_stockreceipt_store_alter_stockreceipt_number_and_more'),
        ('audit', '0004_auditlog_store'),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
