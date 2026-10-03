"""Template helpers for the SSR UI.

Translations are exposed as tags so templates can do ``{% t 'menu.dashboard' %}``
(Django templates cannot call a function with arguments). ``tenum`` builds a key
from a prefix and a model value, e.g. ``{% tenum 'payment' sale.payment_method %}``.
"""
from decimal import Decimal, InvalidOperation

from django import template

from apps.web.i18n import translator

register = template.Library()


def _translator_for(context):
    lang = context.get('brand_lang') or 'uz'
    return translator(lang)


@register.simple_tag(takes_context=True)
def t(context, key, default=None):
    return _translator_for(context)(key, default)


@register.simple_tag(takes_context=True)
def tenum(context, prefix, value):
    if value in (None, ''):
        return ''
    return _translator_for(context)(f'{prefix}.{value}')


@register.filter
def money(value):
    """Format a number with thousands separators (no currency symbol)."""
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return value
    negative = amount < 0
    amount = abs(amount)
    whole = int(amount)
    formatted = f'{whole:,}'.replace(',', ' ')
    return f'-{formatted}' if negative else formatted


@register.filter
def money_full(value, symbol='сом'):
    return f'{money(value)} {symbol}'


@register.filter
def pct(value):
    try:
        return f'{Decimal(str(value or 0)):.0f}%'
    except (InvalidOperation, ValueError):
        return value


@register.simple_tag
def active(request, *url_names):
    """Return 'active' when the current view name matches any given name/prefix."""
    match = getattr(request, 'resolver_match', None)
    if not match:
        return ''
    current = match.view_name
    for name in url_names:
        if current == name or current.startswith(name + ':'):
            return 'active'
    return ''
