"""Barcode generation helpers (EAN-13-like numeric codes)."""
import random

from .models import Product, ProductVariant


def _ean13_check_digit(base12):
    total = 0
    for i, ch in enumerate(base12):
        digit = int(ch)
        total += digit if i % 2 == 0 else digit * 3
    return str((10 - total % 10) % 10)


def generate_barcode():
    """Return a unique 13-digit barcode not used by any product or variant."""
    for _ in range(200):
        base = '20' + ''.join(str(random.randint(0, 9)) for _ in range(10))
        code = base + _ean13_check_digit(base)
        exists = (
            Product.objects.filter(barcode=code).exists()
            or ProductVariant.objects.filter(barcode=code).exists()
        )
        if not exists:
            return code
    raise RuntimeError('Could not generate a unique barcode.')
