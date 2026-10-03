"""Create the single global platform administrator. Idempotent; never resets existing credentials."""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.authentication.models import User


class Command(BaseCommand):
    help = 'Create the platform administrator account (explicit bootstrap only).'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')
        parser.add_argument('--password', default='1')
        parser.add_argument('--pin', default='0808', help='Owner login PIN')
        parser.add_argument('--email', default='admin@brandx.local')

    @transaction.atomic
    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        pin = options['pin']
        email = options['email']

        if User.objects.filter(username=username).exists():
            # Never reset credentials on restart: that would silently hand over
            # the account to whoever controls the environment variables.
            self.stdout.write('Account already exists; credentials unchanged.')
            return

        # Create with the final role in one INSERT: the users table enforces
        # "platform_admin must have no store" at the database level.
        user = User(
            username=username,
            email=email,
            role=User.ROLE_PLATFORM_ADMIN,
            store=None,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        user.set_password(password)
        user.save()
        if pin:
            user.set_pin(pin)
            user.save(update_fields=['pin_hash', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f'Created platform admin "{username}" (password and PIN set).'
        ))
