"""Dashboard page view - reuses the framework-agnostic sales services."""
from datetime import timedelta

from django.db.models import F, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.common.filters import resolve_period
from apps.finance.models import FinanceEntry
from apps.products.models import ProductVariant
from apps.sales import services as sales_services
from apps.sales.models import Sale
from apps.web.decorators import store_required
from apps.web.views.helpers import page_title


def _default_period(request):
    """Use an explicit period, otherwise default to the last 7 days."""
    if request.GET.get('period') or request.GET.get('date_from') or request.GET.get('date_to'):
        return resolve_period(request.GET)
    today = timezone.localdate()
    return today - timedelta(days=6), today


@store_required
def dashboard_view(request):
    store = request.store
    user = request.user
    start, end = _default_period(request)
    period = request.GET.get('period') or 'week'

    context = {
        'page_title': page_title(request, 'dashboard.title'),
        'period': period,
        'date_from': start.isoformat() if start else '',
        'date_to': end.isoformat() if end else '',
        'is_cashier': getattr(user, 'is_cashier', False),
        'can_view_financials': user.can_view_financials,
    }

    if getattr(user, 'is_cashier', False):
        own = sales_services.sales_in_range(start, end, store=store).filter(cashier=user)
        context['my_sales'] = {
            'sales_count': own.count(),
            'revenue': own.aggregate(t=Sum('total_amount'))['t'] or 0,
        }
        return render(request, 'web/dashboard.html', context)

    operational = sales_services.operational_stats(start, end, store=store)
    context['operational'] = operational
    context['top_products'] = sales_services.top_products(start, end, 5, store=store)
    context['chart'] = sales_services.sales_by_day(start, end, store=store) if start and end else []
    context['low_stock'] = (
        ProductVariant.objects.filter(
            store=store, is_active=True, product__is_active=True,
            stock_quantity__lte=F('low_stock_threshold'),
        ).select_related('product', 'color', 'size').order_by('stock_quantity')[:10]
    )
    context['recent_sales'] = Sale.objects.filter(
        store=store, status__in=sales_services.COUNTED_STATUSES
    ).select_related('cashier').order_by('-created_at')[:5]

    if user.can_view_financials:
        context['financial'] = sales_services.financial_stats(start, end, store=store)
        entries = FinanceEntry.objects.filter(store=store, entry_type=FinanceEntry.TYPE_EXPENSE)
        if start:
            entries = entries.filter(entry_date__gte=start)
        if end:
            entries = entries.filter(entry_date__lte=end)
        context['recent_expenses'] = entries.order_by('-entry_date', '-created_at')[:5]

    # Chart bar heights (percentage of the max revenue in the series) and
    # human labels per period: hours for a single-day view, dates otherwise.
    from datetime import datetime as _dt
    chart = context['chart']
    peak = max((point['revenue'] for point in chart), default=0)
    duration = (end - start).days + 1 if start and end else 0
    for point in chart:
        point['height'] = int((point['revenue'] / peak) * 100) if peak else 0
        bucket = _dt.fromisoformat(point['date'])
        point['label'] = bucket.strftime('%H:%M') if duration == 1 else bucket.strftime('%d.%m')

    return render(request, 'web/dashboard.html', context)
