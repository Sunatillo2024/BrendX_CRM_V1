"""
Optional starter data (categories, colours, sizes).

Categories are pure data - the application never hard-codes them.
Run:  python manage.py seed_data
"""
from django.core.management.base import BaseCommand, CommandError
from apps.stores.models import Store

from apps.products.models import Category, Color, Size

CATEGORIES = [
    'Футболка', 'Рубашка', 'Брюки', 'Джинсы', 'Куртка',
    'Платье', 'Шорты', 'Обувь', 'Аксессуары',
]

COLORS = [
    ('Qora', '#000000'), ('Oq', '#FFFFFF'), ('Qizil', '#EF4444'),
    ('Ko\'k', '#2563EB'), ('Yashil', '#16A34A'), ('Sariq', '#FACC15'),
    ('Kulrang', '#6B7280'), ('Jigarrang', '#92400E'), ('Pushti', '#EC4899'),
    ('Ko\'k-och', '#60A5FA'),
]

SIZES = (
    [('XS', 'letter'), ('S', 'letter'), ('M', 'letter'), ('L', 'letter'),
     ('XL', 'letter'), ('XXL', 'letter')]
    + [(str(n), 'numeric') for n in range(28, 46, 2)]
    + [('Universal', 'universal')]
)


class Command(BaseCommand):
    help = 'Load starter categories, colours and sizes (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--store', required=True)

    def handle(self, *args, **options):
        try:
            store = Store.objects.get(code=options['store'].upper())
        except Store.DoesNotExist:
            raise CommandError('Store not found.')
        created = {'categories': 0, 'colors': 0, 'sizes': 0}

        for name in CATEGORIES:
            _, was_created = Category.objects.get_or_create(store=store, name=name)
            created['categories'] += int(was_created)

        for name, hex_code in COLORS:
            _, was_created = Color.objects.get_or_create(
                store=store, name=name, defaults={'hex_code': hex_code}
            )
            created['colors'] += int(was_created)

        for order, (name, size_type) in enumerate(SIZES):
            _, was_created = Size.objects.get_or_create(
                store=store, name=name, size_type=size_type, defaults={'display_order': order}
            )
            created['sizes'] += int(was_created)

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {created['categories']} categories, "
            f"{created['colors']} colours, {created['sizes']} sizes created."
        ))
