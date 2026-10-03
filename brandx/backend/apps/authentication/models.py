"""Authentication App Models - Custom User with Role-Based Access + PIN login"""
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Extended User model with role-based access control.

    Roles:
      - owner   : full access, sees money/cost/profit, manages employees
      - manager : operational access (catalog, stock, sales) without cost/profit
      - cashier : POS + own sales only
    """

    ROLE_PLATFORM_ADMIN = 'platform_admin'
    ROLE_OWNER = 'owner'
    ROLE_MANAGER = 'manager'
    ROLE_CASHIER = 'cashier'

    ROLE_CHOICES = [
        (ROLE_PLATFORM_ADMIN, 'Platform Admin'),
        (ROLE_OWNER, 'Owner'),
        (ROLE_MANAGER, 'Manager'),
        (ROLE_CASHIER, 'Cashier'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CASHIER)
    store = models.ForeignKey('stores.Store', on_delete=models.PROTECT, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    # PIN login - only ever stored as a hash (PBKDF2, same as passwords).
    pin_hash = models.CharField(max_length=128, blank=True)

    # Preferred UI language ('uz' | 'ru')
    language = models.CharField(max_length=5, default='uz')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        constraints = [models.CheckConstraint(
            check=(models.Q(role='platform_admin', store__isnull=True) |
                   models.Q(role__in=['owner', 'manager', 'cashier'], store__isnull=False)),
            name='user_role_store_context',
        )]

    def __str__(self):
        return f'{self.display_name} ({self.get_role_display()})'

    # ── Role helpers ────────────────────────────────────────────────
    @property
    def is_owner(self):
        return self.role == self.ROLE_OWNER

    @property
    def is_manager(self):
        """True for owner and manager (operational access)."""
        return self.role in [self.ROLE_OWNER, self.ROLE_MANAGER]

    @property
    def is_cashier(self):
        return self.role == self.ROLE_CASHIER

    @property
    def can_view_financials(self):
        """Cost price, margin and profit are Owner-only."""
        return self.role == self.ROLE_OWNER

    @property
    def display_name(self):
        full = f'{self.first_name} {self.last_name}'.strip()
        return full or self.username

    # ── PIN helpers ─────────────────────────────────────────────────
    @property
    def has_pin(self):
        return bool(self.pin_hash)

    def set_pin(self, raw_pin):
        """Store the PIN as a one-way hash. Never keep the raw value."""
        self.pin_hash = make_password(str(raw_pin))

    def check_pin(self, raw_pin):
        """Constant-time-ish verification of a raw PIN against the stored hash."""
        if not self.pin_hash:
            return False
        return check_password(str(raw_pin), self.pin_hash)


class PinAttempt(models.Model):
    """
    Failed/successful PIN login attempts, used for throttling.

    Stored in the database (not the cache) so the limit is honoured across
    every gunicorn worker.
    """

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    was_success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'pin_attempts'
        verbose_name = _('PIN attempt')
        verbose_name_plural = _('PIN attempts')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.ip_address} {"ok" if self.was_success else "fail"}'

    @classmethod
    def recent_failures(cls, ip_address, seconds):
        since = timezone.now() - timezone.timedelta(seconds=seconds)
        return cls.objects.filter(
            ip_address=ip_address, was_success=False, created_at__gte=since
        ).count()

    @classmethod
    def reset_failures(cls, ip_address):
        """Clear the failure counter for an IP after a successful login,
        so the attempt budget starts from zero again."""
        if not ip_address:
            return
        cls.objects.filter(ip_address=ip_address, was_success=False).delete()

    @classmethod
    def locked_until(cls, ip_address, max_attempts, lockout_seconds):
        """Return the datetime until which this IP is locked, or None."""
        since = timezone.now() - timezone.timedelta(seconds=lockout_seconds)
        failures = list(
            cls.objects.filter(ip_address=ip_address, was_success=False, created_at__gte=since)
            .order_by('-created_at')
            .values_list('created_at', flat=True)[:max_attempts]
        )
        if len(failures) < max_attempts:
            return None
        lock_expires = failures[0] + timezone.timedelta(seconds=lockout_seconds)
        if lock_expires <= timezone.now():
            return None
        return lock_expires
