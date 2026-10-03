"""Server-rendered UI routes (app_name='web')."""
from django.urls import path

from apps.web import views

app_name = 'web'

urlpatterns = [
    # ── Auth ────────────────────────────────────────────────────────
    path('', views.home_redirect, name='home'),
    path('store/login/', views.login_view, name='login'),
    path('store/<str:code>/login/', views.login_view, name='store-login'),
    path('platform/login/', views.login_view, kwargs={'platform': True}, name='platform-login'),
    path('auth/', views.login_view, name='auth'),
    path('logout/', views.logout_view, name='logout'),
    path('lang/<str:code>/', views.set_language, name='set-language'),

    # ── App pages ───────────────────────────────────────────────────
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('pos/', views.pos_view, name='pos'),
    path('pos/search/', views.pos_search, name='pos-search'),
    path('pos/barcode/', views.pos_barcode, name='pos-barcode'),
    path('pos/checkout/', views.pos_checkout, name='pos-checkout'),

    path('products/', views.product_list, name='product-list'),
    path('products/new/', views.product_form, name='product-create'),
    path('products/barcode/new/', views.product_barcode_new, name='product-barcode-new'),
    path('products/<int:pk>/edit/', views.product_form, name='product-edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product-delete'),
    path('products/<int:pk>/barcode.png', views.product_barcode_image, name='product-barcode'),

    path('categories/', views.category_list, name='category-list'),
    path('categories/save/', views.category_save, name='category-save'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category-delete'),

    path('stock/', views.stock_view, name='stock'),
    path('stock/adjust/', views.stock_adjust, name='stock-adjust'),

    path('receipts/', views.receipts_view, name='receipts'),
    path('receipts/<int:pk>/', views.receipt_detail, name='receipt-detail'),

    path('sales/', views.sales_list, name='sales-list'),
    path('sales/<int:pk>/', views.sale_detail, name='sale-detail'),
    path('sales/<int:pk>/receipt.pdf', views.receipt_pdf, name='receipt-pdf'),
    path('sales/<int:pk>/return/', views.return_items, name='sale-return'),
    path('sales/<int:pk>/cancel/', views.cancel_sale, name='sale-cancel'),

    path('finance/', views.finance_list, name='finance'),
    path('finance/save/', views.finance_save, name='finance-save'),
    path('finance/<int:pk>/delete/', views.finance_delete, name='finance-delete'),

    path('reports/', views.reports_view, name='reports'),
    path('reports/export/<str:kind>/', views.report_export, name='report-export'),

    path('employees/', views.employee_list, name='employees'),
    path('employees/save/', views.employee_save, name='employee-save'),
    path('employees/<int:pk>/set-pin/', views.employee_set_pin, name='employee-set-pin'),
    path('employees/<int:pk>/deactivate/', views.employee_deactivate, name='employee-deactivate'),

    path('settings/', views.settings_view, name='settings'),

    # ── Platform admin ──────────────────────────────────────────────
    path('platform/', views.platform_dashboard, name='platform'),
    path('platform/stores/', views.platform_store_list, name='platform-stores'),
    path('platform/stores/create/', views.platform_store_create, name='platform-store-create'),
    path('platform/stores/<int:pk>/', views.platform_store_detail, name='platform-store-detail'),
    path('platform/stores/<int:pk>/update/', views.platform_store_update, name='platform-store-update'),
    path('platform/stores/<int:pk>/manage-owner/', views.platform_manage_owner, name='platform-manage-owner'),
]
