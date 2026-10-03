"""Shared query helpers used by sales / inventory / finance views."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date

# Period keys understood by every list/report endpoint
PERIOD_TODAY = 'today'
PERIOD_YESTERDAY = 'yesterday'
PERIOD_WEEK = 'week'
PERIOD_MONTH = 'month'
PERIOD_CUSTOM = 'custom'
PERIOD_ALL = 'all'


def resolve_period(params):
    """
    Resolve ``period`` / ``date_from`` / ``date_to`` query params into a
    (start_date, end_date) tuple. Both values are inclusive and may be None.
    """
    period = (params.get('period') or '').strip().lower()
    today = timezone.localdate()

    if period == PERIOD_TODAY:
        return today, today
    if period == PERIOD_YESTERDAY:
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if period == 'days30':
        return today - timedelta(days=29), today
    if period == PERIOD_WEEK:
        return today - timedelta(days=6), today
    if period == PERIOD_MONTH:
        return today.replace(day=1), today
    if period == PERIOD_ALL:
        return None, None

    try:
        start = parse_date(params.get('date_from') or '')
        end = parse_date(params.get('date_to') or '')
    except ValueError:
        raise ValidationError('Invalid date range.')
    if period == PERIOD_CUSTOM or start or end:
        if (params.get('date_from') and not start) or (params.get('date_to') and not end):
            raise ValidationError('Invalid date range.')
        if start and end and (start > end or (end-start).days > 3660):
            raise ValidationError('Invalid or excessively long date range.')
        return start, end
    return None, None


def today_range():
    today = timezone.localdate()
    return today, today


def parse_date_param(value):
    return parse_date(value) if value else None


__all__ = [
    'resolve_period', 'today_range', 'parse_date_param',
    'PERIOD_TODAY', 'PERIOD_YESTERDAY', 'PERIOD_WEEK', 'PERIOD_MONTH',
    'PERIOD_CUSTOM', 'PERIOD_ALL', 'date',
]
