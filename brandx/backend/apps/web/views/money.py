"""Finance (income/expense) and reports pages."""
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.common.filters import resolve_period
from apps.finance.models import FinanceEntry
from apps.reports.views import run_export
from apps.sales import services as sales_services
from apps.web.decorators import manager_required, store_required
from apps.web.forms import FinanceForm
from apps.web.i18n import translator
from apps.web.views.helpers import page_title, paginate, resolve_lang


@manager_required
def finance_list(request):
    store = request.store
    t = translator(resolve_lang(request))

    if request.method == 'POST':
        form = FinanceForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.store = store
            entry.created_by = request.user
            entry.save()
            log_action(
                AuditLog.ACTION_INCOME_CREATED if entry.entry_type == FinanceEntry.TYPE_INCOME
                else AuditLog.ACTION_EXPENSE_CREATED,
                user=request.user, entity='finance_entry', entity_id=entry.pk,
                details={'amount': str(entry.amount), 'category': entry.category})
            messages.success(request, t('common.saved'))
            return redirect('web:finance')
        messages.error(request, t('common.error'))

    qs = FinanceEntry.objects.filter(store=store).select_related('created_by').order_by('-entry_date', '-created_at')
    entry_type = request.GET.get('entry_type') or ''
    if entry_type in ('income', 'expense'):
        qs = qs.filter(entry_type=entry_type)
    period = request.GET.get('period') or ''
    if period:
        start, end = resolve_period(request.GET)
        if start:
            qs = qs.filter(entry_date__gte=start)
        if end:
            qs = qs.filter(entry_date__lte=end)

    scope = FinanceEntry.objects.filter(store=store)
    if entry_type in ('income', 'expense'):
        scope = scope.filter(entry_type=entry_type)
    if period:
        start, end = resolve_period(request.GET)
        if start:
            scope = scope.filter(entry_date__gte=start)
        if end:
            scope = scope.filter(entry_date__lte=end)
    totals = scope.aggregate(
        income=Sum('amount', filter=Q(entry_type=FinanceEntry.TYPE_INCOME)),
        expense=Sum('amount', filter=Q(entry_type=FinanceEntry.TYPE_EXPENSE)))

    page = paginate(request, qs, 20)
    return render(request, 'web/finance.html', {
        'page_title': page_title(request, 'finance.title'),
        'page_obj': page,
        'form': FinanceForm(initial={'entry_date': timezone.localdate()}),
        'entry_type': entry_type,
        'period': period,
        'totals': {
            'income': totals['income'] or 0,
            'expense': totals['expense'] or 0,
            'balance': (totals['income'] or 0) - (totals['expense'] or 0),
        },
    })


@manager_required
def finance_save(request):
    """Create an entry (POST). Reuses the list view's form handling."""
    return finance_list(request)


@manager_required
def finance_delete(request, pk):
    if request.method != 'POST':
        return redirect('web:finance')
    if request.user.role != 'owner':
        return redirect('web:finance')
    entry = get_object_or_404(FinanceEntry, pk=pk, store=request.store)
    log_action(AuditLog.ACTION_FINANCE_DELETED, user=request.user, entity='finance_entry',
               entity_id=entry.pk, details={'amount': str(entry.amount)})
    entry.delete()
    messages.success(request, translator(resolve_lang(request))('common.deleted'))
    return redirect('web:finance')


# ── Reports ─────────────────────────────────────────────────────────
@manager_required
def reports_view(request):
    store = request.store
    period = request.GET.get('period') or 'month'
    params = {'period': period}
    if request.GET.get('date_from'):
        params['date_from'] = request.GET['date_from']
    if request.GET.get('date_to'):
        params['date_to'] = request.GET['date_to']
    start, end = resolve_period(params)

    operational = sales_services.operational_stats(start, end, store=store)
    context = {
        'page_title': page_title(request, 'reports.title'),
        'period': period,
        'date_from': start.isoformat() if start else '',
        'date_to': end.isoformat() if end else '',
        'operational': operational,
        'top_products': sales_services.top_products(start, end, 10, store=store),
        'can_view_financials': request.user.can_view_financials,
        'query_string': request.GET.urlencode(),
    }
    if request.user.can_view_financials:
        context['financial'] = sales_services.financial_stats(start, end, store=store)
    return render(request, 'web/reports.html', context)


def report_export(request, kind):
    """Serve the report file after the same role checks the exports declare."""
    response = run_export(request, kind)
    if response is None:
        messages.error(request, translator(resolve_lang(request))('common.error'))
        return redirect('web:reports')
    return response
