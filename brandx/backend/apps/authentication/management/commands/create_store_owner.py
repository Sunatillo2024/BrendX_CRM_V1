import getpass
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.stores.models import Store
from apps.stores.services import make_owner
from apps.authentication.validators import validate_pin_format, pin_is_taken


class Command(BaseCommand):
    help = 'Provision the first owner of an existing store; prompts for a private PIN.'

    def add_arguments(self, parser):
        parser.add_argument('--store', required=True)
        parser.add_argument('--name', required=True)
        parser.add_argument('--language', choices=['uz', 'ru'], default='ru')

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            store = Store.objects.select_for_update().get(code=options['store'].upper())
        except Store.DoesNotExist:
            raise CommandError('Store not found.')
        if store.user_set.filter(role='owner').exists():
            raise CommandError('Owner already exists; manage it through the platform panel.')
        pin = getpass.getpass('Owner PIN: ')
        if pin != getpass.getpass('Confirm PIN: '):
            raise CommandError('PINs do not match.')
        try:
            pin = validate_pin_format(pin)
        except Exception:
            raise CommandError('PIN must contain 4–8 digits.')
        if pin_is_taken(pin, store=store):
            raise CommandError('PIN already used in this store.')
        make_owner(store, options['name'], pin, options['language'])
        self.stdout.write(self.style.SUCCESS('Store owner created.'))
