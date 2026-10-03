"""Server-rendered UI views (re-exported for apps.web.urls)."""
from apps.web.views.auth import (  # noqa: F401
    home_redirect, login_view, logout_view, set_language,
)
from apps.web.views.catalog import (  # noqa: F401
    category_delete, category_list, category_save, product_barcode_image,
    product_barcode_new, product_delete, product_form, product_list,
)
from apps.web.views.dashboard import dashboard_view  # noqa: F401
from apps.web.views.inventory import (  # noqa: F401
    pos_barcode, pos_search, receipt_detail, receipts_view, stock_adjust, stock_view,
)
from apps.web.views.money import (  # noqa: F401
    finance_delete, finance_list, finance_save, report_export, reports_view,
)
from apps.web.views.people import (  # noqa: F401
    employee_deactivate, employee_list, employee_save, employee_set_pin, settings_view,
)
from apps.web.views.platform import (  # noqa: F401
    platform_dashboard, platform_manage_owner, platform_store_create,
    platform_store_detail, platform_store_list, platform_store_update,
)
from apps.web.views.sales import (  # noqa: F401
    cancel_sale, pos_checkout, pos_view, receipt_pdf, return_items, sale_detail, sales_list,
)
