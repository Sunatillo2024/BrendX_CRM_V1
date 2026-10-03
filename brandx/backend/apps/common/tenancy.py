"""Store-tenancy helpers shared by services and views (DRF-free).

``active_store`` raises ``django.core.exceptions.PermissionDenied``, which
Django's handler converts into an HTTP 403 response.
"""

STORE_PATHS = {
    'productvariant': 'store', 'product': 'store', 'category': 'store',
    'color': 'store', 'size': 'store', 'user': 'store', 'customer': 'store',
    'vendor': 'store', 'financeentry': 'store', 'sale': 'store',
    'stockreceipt': 'store', 'auditlog': 'store',
    'saleitem': 'sale__store', 'receipt': 'sale__store',
    'salereturn': 'sale__store', 'salereturnitem': 'sale_return__sale__store',
    'stockmovement': 'product_variant__store', 'stockreceiptitem': 'receipt__store',
    'vendortransaction': 'vendor__store',
}


def active_store(user):
    from django.core.exceptions import PermissionDenied
    if not user or not user.is_authenticated or user.role == 'platform_admin' or not user.store_id:
        raise PermissionDenied('Store account required.')
    if not user.is_active or not user.store.is_active:
        raise PermissionDenied('Store access is disabled.')
    return user.store


def scope(queryset, store):
    from django.core.exceptions import PermissionDenied
    if store is None:
        raise PermissionDenied('Store context required.')
    path = STORE_PATHS.get(queryset.model._meta.model_name)
    if not path:
        raise PermissionDenied('Unsupported tenant entity.')
    return queryset.filter(**{path: store.pk})
