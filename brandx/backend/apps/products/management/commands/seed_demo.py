"""
Full demo dataset for a store: owner + staff, catalog with generated images,
vendors, customers, stock receipts, sales history and finance entries.

Media images (avatars, category tiles, product photos) are generated with
Pillow and stored under MEDIA_ROOT (media/...).

Run:   python manage.py seed_demo
Wipe:  python manage.py seed_demo --flush
"""
import os
import random
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.authentication.models import User
from apps.customers.models import Customer
from apps.finance.models import FinanceEntry
from apps.inventory import services as inventory_services
from apps.inventory.models import StockMovement, StockReceipt
from apps.products.models import Category, Color, Product, ProductVariant, Size
from apps.products.utils import generate_barcode
from apps.sales.models import Receipt, Sale, SaleItem, SaleReturn
from apps.stores.models import Store
from apps.vendors.models import Vendor

STORE_CODE = 'DEMO'

# ── Reference data ──────────────────────────────────────────────────
CATEGORIES = [
    ('Futbolka', 'tshirt', '#3B82F6'),
    ('Rubashka', 'shirt', '#10B981'),
    ('Shim', 'pants', '#8B5CF6'),
    ('Jinsi', 'pants', '#2563EB'),
    ('Kurtka', 'jacket', '#F59E0B'),
    ("Ko'ylak", 'dress', '#EC4899'),
    ('Krasovka', 'shoes', '#EF4444'),
    ('Aksessuar', 'belt', '#6B7280'),
]

COLORS = [
    ('Qora', '#111827'), ('Oq', '#F9FAFB'), ('Qizil', '#EF4444'),
    ("Ko'k", '#2563EB'), ('Yashil', '#16A34A'), ('Sariq', '#FACC15'),
    ('Kulrang', '#9CA3AF'), ('Pushti', '#EC4899'), ('Jigarrang', '#92400E'),
]

SIZES = ([('XS', 'letter'), ('S', 'letter'), ('M', 'letter'), ('L', 'letter'),
          ('XL', 'letter'), ('XXL', 'letter')]
         + [(str(n), 'numeric') for n in range(38, 46, 2)]
         + [('Universal', 'universal')])

PRODUCTS = [
    {'name': 'Futbolka Premium', 'category': 'Futbolka', 'icon': 'tshirt',
     'cost': 350, 'price': 890, 'bg': '#DBEAFE',
     'variants': [('Oq', 'M'), ('Oq', 'L'), ('Qora', 'M'), ('Qora', 'XL'),
                  ("Ko'k", 'L'), ("Ko'k", 'XL')]},
    {'name': 'Rubashka Klassik', 'category': 'Rubashka', 'icon': 'shirt',
     'cost': 620, 'price': 1450, 'bg': '#D1FAE5',
     'variants': [('Oq', 'M'), ('Oq', 'L'), ('Kulrang', 'L'), ('Yashil', 'XL')]},
    {'name': 'Sport Shim', 'category': 'Shim', 'icon': 'pants',
     'cost': 480, 'price': 1190, 'bg': '#EDE9FE',
     'variants': [('Qora', 'M'), ('Qora', 'L'), ("Ko'k", 'XL'), ('Kulrang', 'L')]},
    {'name': 'Jinsi Slim Fit', 'category': 'Jinsi', 'icon': 'pants',
     'cost': 950, 'price': 2290, 'bg': '#DBEAFE',
     'variants': [("Ko'k", '38'), ("Ko'k", '40'), ('Qora', '40'), ('Qora', '42')]},
    {'name': 'Kurtka Winter', 'category': 'Kurtka', 'icon': 'jacket',
     'cost': 1800, 'price': 4390, 'bg': '#FEF3C7',
     'variants': [('Qora', 'L'), ('Qora', 'XL'), ('Yashil', 'M'), ('Sariq', 'L')]},
    {'name': "Ko'ylak Yozgi", 'category': "Ko'ylak", 'icon': 'dress',
     'cost': 750, 'price': 1890, 'bg': '#FCE7F3',
     'variants': [('Qizil', 'S'), ('Qizil', 'M'), ('Pushti', 'M'), ('Pushti', 'L')]},
    {'name': 'Krossovka Air', 'category': 'Krasovka', 'icon': 'shoes',
     'cost': 1450, 'price': 3590, 'bg': '#FEE2E2',
     'variants': [('Oq', '40'), ('Oq', '42'), ('Qora', '42'), ('Qora', '44')]},
    {'name': 'Kamar Classic', 'category': 'Aksessuar', 'icon': 'belt',
     'cost': 260, 'price': 690, 'bg': '#F3F4F6',
     'variants': [('Qora', 'Universal'), ('Jigarrang', 'Universal')]},
]

STAFF = [
    {'username': 'demo-owner', 'first_name': 'Aziz Rahimov', 'role': 'owner',
     'pin': '1234', 'phone': '+998 90 111 22 33', 'color': '#2563EB'},
    {'username': 'demo-manager', 'first_name': 'Dilnoza Karimova', 'role': 'manager',
     'pin': '2222', 'phone': '+998 90 444 55 66', 'color': '#16A34A'},
    {'username': 'demo-cashier', 'first_name': 'Sardor Aliyev', 'role': 'cashier',
     'pin': '3333', 'phone': '+998 90 777 88 99', 'color': '#F59E0B'},
]

VENDORS = [
    {'name': 'Tekstil Optom MChJ', 'phone': '+998 71 200 10 10',
     'contact_person': 'Bobur Ismoilov', 'company_name': 'Tekstil Optom MChJ'},
    {'name': 'Osiyo Import Savdo', 'phone': '+998 71 300 20 20',
     'contact_person': 'Malika Yusupova', 'company_name': 'Osiyo Import Savdo LLC'},
]

CUSTOMERS = [
    {'name': 'Alisher Nazarov', 'phone': '+998 93 555 11 22'},
    {'name': 'Nodira Qodirova', 'phone': '+998 94 666 33 44'},
    {'name': "Mirzo Ulug'bek", 'phone': '+998 97 777 55 66'},
]

FINANCE = [
    {'entry_type': 'expense', 'amount': 8_500_000, 'category': 'rent',
     'comment': 'Do`kon ijarasi', 'days_ago': 25},
    {'entry_type': 'expense', 'amount': 15_000_000, 'category': 'salary',
     'comment': 'Xodimlar oylik', 'days_ago': 20},
    {'entry_type': 'expense', 'amount': 1_250_000, 'category': 'utilities',
     'comment': 'Elektr va suv', 'days_ago': 15},
    {'entry_type': 'income', 'amount': 480_000, 'category': 'other',
     'comment': 'Eski quti sotuvi', 'days_ago': 10},
]

PAYMENT_CYCLE = [Sale.PAYMENT_CASH, Sale.PAYMENT_CARD, Sale.PAYMENT_MIXED,
                 Sale.PAYMENT_CASH, Sale.PAYMENT_CARD, Sale.PAYMENT_CASH]


# ── Image generation (Pillow) ───────────────────────────────────────
FONT_CANDIDATES = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
    '/Library/Fonts/Arial Bold.ttf',
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
]


def _font(size):
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _center_text(draw, cx, cy, text, font, fill):
    box = draw.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.text((cx - w / 2 - box[0], cy - h / 2 - box[1]), text, font=font, fill=fill)


def _png(image):
    buf = BytesIO()
    image.save(buf, format='PNG')
    return buf.getvalue()


def make_avatar(initials, color):
    """Round avatar with initials."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (256, 256), '#FFFFFF')
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 248, 248], fill=color)
    _center_text(draw, 128, 132, initials, _font(96), '#FFFFFF')
    return _png(img)


def make_category_tile(name, color):
    """Square tile with a big first letter and the category name."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (512, 512), color)
    draw = ImageDraw.Draw(img)
    letter = name[0].upper()
    _center_text(draw, 256, 200, letter, _font(220), '#FFFFFF')
    _center_text(draw, 256, 420, name, _font(52), '#FFFFFF')
    return _png(img)


def _draw_icon(draw, icon, cx, cy, scale, fill):
    """Very simple garment silhouettes."""
    s = scale
    if icon == 'tshirt':
        draw.polygon([(cx - 3 * s, cy - 1 * s), (cx - 2 * s, cy - 3 * s),
                      (cx - 1 * s, cy - 3.5 * s), (cx + 1 * s, cy - 3.5 * s),
                      (cx + 2 * s, cy - 3 * s), (cx + 3 * s, cy - 1 * s),
                      (cx + 1.5 * s, cy + 0.5 * s), (cx + 1.5 * s, cy + 3.5 * s),
                      (cx - 1.5 * s, cy + 3.5 * s), (cx - 1.5 * s, cy + 0.5 * s)], fill=fill)
    elif icon == 'shirt':
        draw.polygon([(cx - 2.6 * s, cy - 0.6 * s), (cx - 1.6 * s, cy - 3.2 * s),
                      (cx + 1.6 * s, cy - 3.2 * s), (cx + 2.6 * s, cy - 0.6 * s),
                      (cx + 1.6 * s, cy + 3.2 * s), (cx - 1.6 * s, cy + 3.2 * s)], fill=fill)
        draw.line([(cx, cy - 3.2 * s), (cx, cy + 3.2 * s)], fill='#FFFFFF', width=max(2, s // 3))
    elif icon == 'pants':
        draw.polygon([(cx - 2 * s, cy - 3.5 * s), (cx + 2 * s, cy - 3.5 * s),
                      (cx + 1.4 * s, cy + 3.5 * s), (cx + 0.3 * s, cy + 3.5 * s),
                      (cx, cy - 0.5 * s), (cx - 0.3 * s, cy + 3.5 * s),
                      (cx - 1.4 * s, cy + 3.5 * s)], fill=fill)
    elif icon == 'dress':
        draw.polygon([(cx - 1.2 * s, cy - 3.5 * s), (cx + 1.2 * s, cy - 3.5 * s),
                      (cx + 2.6 * s, cy + 3.5 * s), (cx - 2.6 * s, cy + 3.5 * s)], fill=fill)
    elif icon == 'jacket':
        draw.polygon([(cx - 2.6 * s, cy - 0.8 * s), (cx - 1.8 * s, cy - 3.5 * s),
                      (cx + 1.8 * s, cy - 3.5 * s), (cx + 2.6 * s, cy - 0.8 * s),
                      (cx + 1.6 * s, cy + 3.5 * s), (cx - 1.6 * s, cy + 3.5 * s)], fill=fill)
        draw.line([(cx, cy - 3.5 * s), (cx, cy + 3.5 * s)], fill='#FFFFFF', width=max(2, s // 3))
    elif icon == 'shoes':
        draw.ellipse([cx - 3 * s, cy - 1.2 * s, cx + 3 * s, cy + 2 * s], fill=fill)
        draw.rectangle([cx - 3 * s, cy + 1.2 * s, cx + 3 * s, cy + 2 * s], fill='#111827')
    elif icon == 'belt':
        draw.rounded_rectangle([cx - 3.2 * s, cy - 0.9 * s, cx + 3.2 * s, cy + 0.9 * s],
                               radius=s // 3, fill=fill)
        draw.rounded_rectangle([cx - 0.8 * s, cy - 1.4 * s, cx + 0.8 * s, cy + 1.4 * s],
                               radius=s // 4, outline='#FFFFFF', width=max(2, s // 3))
    else:
        draw.ellipse([cx - 3 * s, cy - 3 * s, cx + 3 * s, cy + 3 * s], fill=fill)


def make_product_image(name, icon, bg, price):
    """Product placeholder: light background, garment icon, name and price."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (640, 640), bg)
    draw = ImageDraw.Draw(img)
    _draw_icon(draw, icon, 320, 250, 52, '#111827')
    _center_text(draw, 320, 520, name, _font(44), '#111827')
    _center_text(draw, 320, 580, f'{price:,.0f} so`m'.replace(',', ' '), _font(36), '#4B5563')
    return _png(img)


# ── The command ─────────────────────────────────────────────────────
class Command(BaseCommand):
    help = 'Create a demo store with fake data (staff, catalog, stock, sales, finance).'

    def add_arguments(self, parser):
        parser.add_argument('--code', default=STORE_CODE, help='Store code to create.')
        parser.add_argument('--flush', action='store_true',
                            help='Delete the demo store data first, then recreate it.')

    def handle(self, *args, **options):
        code = options['code'].upper()
        if options['flush']:
            self._flush(code)
        elif Store.objects.filter(code=code).exists():
            raise CommandError(
                f'Store "{code}" already exists. Use --flush to recreate it.')
        with transaction.atomic():
            store = self._create_store(code)
            staff = self._create_staff(store)
            self._create_catalog(store)
            vendors, customers = self._create_parties(store)
            self._create_stock(store, staff['owner'], vendors)
            self._create_sales(store, staff)
            self._create_finance(store, staff['owner'])
        self._print_summary(code)

    # ── flush ───────────────────────────────────────────────────────
    def _flush(self, code):
        store = Store.objects.filter(code=code).first()
        if not store:
            return
        files = []
        for model, field in [(Product, 'image'), (Category, 'image'), (User, 'avatar')]:
            for obj in model.objects.filter(store=store):
                f = getattr(obj, field)
                if f:
                    try:
                        files.append(f.path)
                    except (ValueError, NotImplementedError):
                        pass
        for model in [AuditLog, SaleReturn, Receipt, Sale, StockMovement,
                      StockReceipt, FinanceEntry, VendorTransaction,
                      ProductVariant, Product, Category, Color, Size,
                      Vendor, Customer, User]:
            qs = model.objects.filter(store=store) if model is not User \
                else model.objects.filter(store=store)
            try:
                qs.delete()
            except Exception:
                for obj in list(qs):
                    obj.delete()
        store.delete()
        for path in files:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self.stdout.write(self.style.WARNING(f'Store "{code}" wiped.'))

    # ── creators ────────────────────────────────────────────────────
    def _create_store(self, code):
        return Store.objects.create(
            name='BrandX Demo Fashion', code=code,
            phone='+998 90 123 45 67',
            address='Toshkent sh., Amir Temur shoh kochasi 12',
            receipt_header='BrandX Demo Fashion',
            receipt_footer='Xaridingiz uchun rahmat!',
            currency_code='KGS', currency_symbol='сом',
            low_stock_threshold=5, default_language='uz', timezone='Asia/Tashkent',
            notes='Demo do`kon - test ma`lumotlari.',
        )

    def _create_staff(self, store):
        from django.core.files.base import ContentFile
        staff = {}
        initials = {'owner': 'AR', 'manager': 'DK', 'cashier': 'SA'}
        for row in STAFF:
            user, created = User.objects.get_or_create(
                username=row['username'],
                defaults={'first_name': row['first_name'], 'role': row['role'],
                          'store': store, 'phone': row['phone'], 'language': 'uz'})
            user.set_unusable_password()
            user.set_pin(row['pin'])
            user.save()
            if created or not user.avatar:
                user.avatar.save(
                    f"{row['username']}.png",
                    ContentFile(make_avatar(initials[row['role']], row['color'])),
                    save=True)
            staff[row['role']] = user
        return staff

    def _create_catalog(self, store):
        from django.core.files.base import ContentFile
        colors = {name: Color.objects.get_or_create(
            store=store, name=name, defaults={'hex_code': hex})[0]
            for name, hex in COLORS}
        sizes = {name: Size.objects.get_or_create(
            store=store, name=name, size_type=kind, defaults={'display_order': i})[0]
            for i, (name, kind) in enumerate(SIZES)}

        categories = {}
        for name, icon, color in CATEGORIES:
            category, created = Category.objects.get_or_create(
                store=store, name=name,
                defaults={'description': f'{name} toifasi (demo)'})
            if created or not category.image:
                category.image.save(
                    f'{name}.png', ContentFile(make_category_tile(name, color)), save=True)
            categories[name] = category

        self.variants = []
        for spec in PRODUCTS:
            product, created = Product.objects.get_or_create(
                store=store, name=spec['name'],
                defaults={'description': f"{spec['name']} - sifatli mahsulot (demo).",
                          'category': categories[spec['category']],
                          'barcode': generate_barcode(),
                          'base_cost_price': Decimal(spec['cost']),
                          'base_selling_price': Decimal(spec['price'])})
            if created or not product.image:
                product.image.save(
                    f"{spec['name']}.png",
                    ContentFile(make_product_image(
                        spec['name'], spec['icon'], spec['bg'], spec['price'])),
                    save=True)
            for color_name, size_name in spec['variants']:
                variant = ProductVariant.objects.create(
                    store=store, product=product, color=colors[color_name],
                    size=sizes[size_name], sku=generate_barcode(),
                    barcode=generate_barcode(),
                    selling_price=Decimal(spec['price']),
                    cost_price=Decimal(spec['cost']))
                self.variants.append(variant)

    def _create_parties(self, store):
        vendors = []
        for row in VENDORS:
            vendor, _ = Vendor.objects.get_or_create(
                store=store, name=row['name'], defaults=row)
            vendors.append(vendor)
        customers = []
        for row in CUSTOMERS:
            customer, _ = Customer.objects.get_or_create(
                store=store, name=row['name'], defaults=row)
            customers.append(customer)
        return vendors, customers

    def _create_stock(self, store, owner, vendors):
        rng = random.Random(42)
        items = [{'product_variant': v, 'quantity': rng.randint(15, 40),
                  'cost_price': v.effective_cost} for v in self.variants]
        half = len(items) // 2
        inventory_services.receive_stock(
            items=items[:half], user=owner, vendor=vendors[0],
            receipt_date=timezone.localdate() - timedelta(days=12),
            notes='Boshlang`ich qoldiq (demo)')
        inventory_services.receive_stock(
            items=items[half:], user=owner, vendor=vendors[1],
            receipt_date=timezone.localdate() - timedelta(days=9),
            notes='Ikkinchi partiya (demo)')

    def _create_sales(self, store, staff):
        rng = random.Random(7)
        cashiers = [staff['cashier'], staff['manager'], staff['owner']]
        for i in range(6):
            when = timezone.now() - timedelta(days=9 - i, hours=-(i % 5))
            picks = rng.sample(self.variants, k=rng.randint(1, 3))
            lines = []
            for variant in picks:
                qty = rng.randint(1, 2)
                price = variant.effective_price
                lines.append((variant, qty, price, rng.choice([0, 0, 5, 10])))
            subtotal = sum(
                Decimal(q) * p * (1 - Decimal(d) / 100) for _, q, p, d in lines)
            total = subtotal.quantize(Decimal('0.01'))

            method = PAYMENT_CYCLE[i % len(PAYMENT_CYCLE)]
            if method == Sale.PAYMENT_CASH:
                received = (total // 1000 + 1) * 1000
                cash, card, change = total, Decimal('0'), received - total
            elif method == Sale.PAYMENT_CARD:
                received, cash, card, change = total, Decimal('0'), total, Decimal('0')
            else:
                cash = (total * Decimal('0.5')).quantize(Decimal('0.01'))
                card = total - cash
                received, change = cash, Decimal('0')

            sale = Sale.objects.create(
                number=store.next_number('sale'), store=store,
                customer=Customer.objects.filter(store=store)[i % 3],
                cashier=cashiers[i % len(cashiers)],
                payment_method=method,
                subtotal=sum(Decimal(q) * p for _, q, p, _ in lines).quantize(Decimal('0.01')),
                discount_amount=sum(
                    (Decimal(q) * p * Decimal(d) / 100) for _, q, p, d in lines
                ).quantize(Decimal('0.01')),
                tax_amount=Decimal('0'), total_amount=total,
                cash_amount=cash, card_amount=card,
                received_amount=received, change_amount=change)
            for variant, qty, price, discount in lines:
                SaleItem.objects.create(
                    sale=sale, product_variant=variant,
                    product_name=variant.product.name,
                    color_name=variant.color.name if variant.color else '',
                    size_name=variant.size.name if variant.size else '',
                    quantity=qty, unit_price=price,
                    unit_cost=variant.effective_cost, discount_percent=discount)
                inventory_services.sell_stock(variant, qty, sale, user=staff['owner'])
            Receipt.objects.create(sale=sale, receipt_number=sale.sale_number)
            # Backdate so dashboards/reports show a realistic history
            Sale.objects.filter(pk=sale.pk).update(created_at=when, updated_at=when)
            Receipt.objects.filter(sale=sale).update(generated_at=when)
            StockMovement.objects.filter(sale=sale).update(created_at=when)

    def _create_finance(self, store, owner):
        for row in FINANCE:
            FinanceEntry.objects.create(
                store=store, entry_type=row['entry_type'],
                amount=Decimal(row['amount']), category=row['category'],
                comment=row['comment'],
                entry_date=timezone.localdate() - timedelta(days=row['days_ago']),
                created_by=owner)

    # ── summary ─────────────────────────────────────────────────────
    def _print_summary(self, code):
        base = 'http://localhost:8000'
        lines = [
            '',
            self.style.SUCCESS(f'Demo store "{code}" created!'),
            '',
            '  Login (store login + PIN):',
            '    owner   : PIN 1234   (Aziz Rahimov)',
            '    manager : PIN 2222   (Dilnoza Karimova)',
            '    cashier : PIN 3333   (Sardor Aliyev)',
            '',
            f'  Login page : {base}/store/{code.lower()}/login/',
            f'  Dashboard  : {base}/dashboard/',
            f'  POS        : {base}/pos/',
            f'  Products   : {base}/products/',
            f'  Media      : {base}/media/  (avatars/, categories/, products/)',
        ]
        self.stdout.write('\n'.join(lines))
