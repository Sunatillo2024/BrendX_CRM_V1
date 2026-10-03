"""PIN validation helpers shared by the web UI and management commands.

These used to live in ``authentication.serializers`` (DRF); they are plain
Django validators so the server-rendered app needs no DRF dependency.
"""
from django.conf import settings as dj_settings
from django.core.exceptions import ValidationError

from .models import User


def validate_pin_format(value):
    if not value or not str(value).isdigit():
        raise ValidationError('PIN must contain digits only.')
    min_len = getattr(dj_settings, 'PIN_MIN_LENGTH', 4)
    max_len = getattr(dj_settings, 'PIN_MAX_LENGTH', 8)
    if not (min_len <= len(str(value)) <= max_len):
        raise ValidationError(f'PIN must be {min_len}-{max_len} digits long.')
    return str(value)


def pin_is_taken(pin, exclude_user_id=None, store=None):
    """PINs must be unique, otherwise PIN login cannot identify the employee."""
    qs = User.objects.filter(is_active=True, store=store).exclude(pin_hash='')
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)
    for user in qs.only('id', 'pin_hash'):
        if user.check_pin(pin):
            return True
    return False
