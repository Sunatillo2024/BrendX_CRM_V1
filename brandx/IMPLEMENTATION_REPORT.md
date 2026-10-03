# Implementation Report — BrandX → Clothes Shop CRM/POS

> **2026-10-03 update:** the DRF/JWT API layer and the Angular 19 frontend have
> since been removed; the UI is now fully server-rendered Django templates with
> session auth (see README.md). This report is kept as a historical record —
> references to DRF, JWT, Angular and `/api/*` below describe the earlier
> architecture.

## Architecture update checkpoint — 2026-10-01

**Status (2026-10-01): implemented and verified on PostgreSQL 17.** Evidence:
145 backend tests (PG + SQLite), clean migration-drift check, production Angular
build, a 24/24 live multi-store smoke test, and a real MySQL → PostgreSQL data
cutover rehearsal on the development database. Remaining production cautions are
listed under *Remaining Issues*. Sections further below describe the original
single-store starting point.

### PostgreSQL Migration

- PostgreSQL 17 is the primary configured backend; psycopg 3.2.13 added.
- MySQL-only connection options are conditional for source transfer. Hardcoded
  Django DB credentials removed. Startup readiness uses Django's DB connection.
- Docker adds an independent PostgreSQL volume and retains MySQL under a legacy
  profile. Existing MySQL source/media are not deleted or switched live.
- Bootstrap/seed disabled by default so an import target remains empty and
  container restarts do not automatically reset account credentials.
- POS locks only the variant table to avoid PostgreSQL nullable-outer-join locks.
- `transfer_database export/import/verify` preserves IDs, PIN/password hashes,
  Decimal snapshots and relationships; checks counts/content digests and database
  constraints, resets sequences and rolls back invalid imports. Nonempty targets
  and archive overwrites are refused. Auth permissions use natural keys.
- README documents backup, frozen writes, protected archives, media, schema-version
  matching, token invalidation, operator cutover and rollback limitations.
- MySQL source/media volumes were **not** deleted: MySQL stays available under
  the `legacy-mysql` profile as the rollback source.
- **Cutover rehearsed on the development database (2026-10-01):** native
  `mysqldump` backup (`backups/brandx-mysql-before-transfer.sql`, 31 tables),
  Store schema + BrandX backfill applied to MySQL, `transfer_database export`
  (97 records, mode 0600), fresh PostgreSQL migrate, `import` + `verify` (all model
  counts/digests/relationships matched), sequence reset, backend restart. Migrated:
  1 store, 3 users, 1 product, 2 variants, 3 sales, 3 sale items, 5 stock
  movements, 34 audit rows. No MySQL rows were deleted.

### Multi-Store Architecture

Implemented: shared PostgreSQL database with an explicit `store` FK on every
tenant-root entity (users, categories, colours, sizes, products, variants, sales,
receipts, returns, finance entries, customers, vendors, stock receipts, audit logs)
and parent-scoped children (sale items, movements, receipt items). A data migration
backfills all pre-existing rows into **BrandX** before NOT NULL/enforcement
constraints are added. Store codes/barcodes/SKUs/names are unique **per store**;
sale and receipt numbers are allocated from per-store counters locked with
`select_for_update`. Store login uses `/store/<CODE>/login` + PIN with identical
PINs allowed across stores.

### Platform Admin

Implemented: `platform_admin` is a global role (DB check constraint forces
`store IS NULL`, other roles force `store IS NOT NULL`). Dedicated `/platform`
UI + `/api/platform/*` endpoints (dashboard counts, create/edit store with first
owner in one transaction, manage owner, activate/deactivate) are gated by
`IsPlatformAdmin`; owners get 403. The legacy `admin` account is migrated to
platform admin and is the only technical-Django-admin credential; store accounts
are refused at `/admin/`.

### Owner / Manager / Cashier

Implemented. Owner: full store scope, employees/finance/reports/audit/store
settings; cannot create stores, reach `/platform`, assign `platform_admin`, or
edit/deactivate the owner. Manager: same operational scope with no cost/profit
payloads and no audit/receipt-cost export. Cashier: POS + own sales only. Store
deactivation blocks logins **and** already-issued JWT/refresh tokens; reactivation
restores access without touching data. Employee `store_id` always comes from the
authenticated owner (client-supplied `store` is ignored).

### Product Workflow

Implemented: **simple product mode** (no colour/size, one stock number),
**size × colour stock matrix** that creates the required variants in one atomic,
store-locked request, **inline category creation** without leaving the form,
**barcode generate/duplicate-check** with per-store uniqueness and the Russian
error message from the brief, and **product duplication** (`/products/new?duplicate=<id>`).
Every stock write goes through `change_stock`, so products now always produce a
`StockMovement`; non-owners cannot write `cost_price`/`base_cost_price`.

### Statistics

Implemented and covered by tests:

- Revenue = sale totals − period refunds (fully refunded sales are no longer
  double-subtracted); returns are excluded from cancelled sales.
- COGS = historical `SaleItem.unit_cost` (never current purchase price) − returned
  cost; changing `Product.base_cost_price` does not rewrite past profit.
- Gross Profit = Revenue − COGS; **Net Profit = Gross Profit − Expenses**, with
  other income reported separately (it no longer inflates net profit).
- Average receipt = net revenue ÷ sale count; cash/card split is reduced by the
  refund allocation (each `SaleReturn` stores its cash/card parts).
- Refunds honour line + sale-wide discounts, allocate the paid amount in cents
  (last line absorbs rounding), run under row locks, reject duplicate/over refunds
  and cap at the sale total.
- Units sold and top products subtract returns and use stable product IDs.
- Chart granularity: hourly for 1 day, daily ≤ 90 days, weekly beyond, with all
  buckets filled; refunds shown as negative revenue. Dashboard KPIs, recent sales
  and expenses share the selected date range (custom ranges validated server-side).

### Security

Implemented: every list/detail/custom action resolves querysets through
`apps/common/tenancy.py` (fail-closed — no store context means deny), writable
related fields are re-scoped inside serializers (a client cannot post another
store's product/variant/vendor/customer ID), services validate tenant inputs,
exports and statistics take an explicit store, AI analysis is owner-only and
store-bound, and audit rows carry the store. Verified by 12 two-store API tests,
3 real-PostgreSQL concurrency tests and 24 live HTTP checks (read IDOR, write
IDOR, cross-store POS, export leakage, stats leakage, deactivation/token revocation,
platform authorization, old JWT).

### Tests

- **PostgreSQL 17.11: 145 tests OK** (24 new: multi-store isolation, platform API,
  provisioning, deactivation, discounted/roll-back returns, receipt/store settings,
  chart ranges, transfer integrity, legacy backfill migration, 3 concurrency tests
  for oversell / duplicate numbering / double refund).
- **SQLite: 145 tests OK** (the 3 PostgreSQL-only concurrency tests skip).
- **Migration drift:** `makemigrations --check --dry-run` → no changes.
- **Frontend:** `ng build --configuration production` succeeds in Docker.
- **Live stack smoke:** `python3 verify_multistore.py` → **24/24 checks** against
  the running Docker stack (web, platform login/dashboard, store+owner creation,
  store-link login, platform 403, category/simple product/stock movement,
  per-store barcode uniqueness, cross-store 404, POS + change, store receipt PDF,
  export scoping, dashboards, deactivation/reactivation, admin PIN page).
- **Data cutover rehearsal:** mysqldump backup → MySQL migrate + BrandX backfill →
  export (97 records) → fresh PostgreSQL migrate → import + verify → all counts,
  content digests and relationships matched.

### Removed Code

No business functionality removed. Replaced MySQL-only startup readiness and
hardcoded Django DB credentials; `create_admin` no longer resets credentials on
every boot and now provisions a platform admin only when explicitly bootstrapped.
The legacy single-store `verify_e2e.py` script no longer matches the store-link
login API — `verify_multistore.py` supersedes it. Temporary `mysqlclient`
dependency is retained only for source-database access; remove it after the final
source cutover once no MySQL connection remains (reference-check first).

### Remaining Issues

- **Django 5.0.4 is no longer supported** (October 2026). Upgrade to a tested
  Django LTS release and re-run the full suite before calling this production-ready.
- Run this full verification against a **copy of real production data**, not just
  the development database; rehearse rollback (MySQL is preserved but stale once
  PostgreSQL accepts writes).
- Rotate `SECRET_KEY` at controlled cutover to invalidate pre-migration JWTs, and
  delete/retire the transfer archive (it contains password/PIN hashes) after sign-off.
- Archives are held in memory — assess very large databases before scheduling the
  production window. Media files are transferred separately (not part of the archive).
- `django_filters`/`SearchFilter` page-size parameters and the old English strings
  in a few backend messages were not audited for copy quality; RU/UZ UI copy review
  remains manual. Browser-level (Playwright/Selenium) coverage is not automated.
- Per-store `Store.default_language` is not yet applied automatically at store
  creation time for employees (owner chooses language explicitly).

---

Adaptation of the existing BrandX CRM/POS into a simple, fast system for a single
clothes shop. The existing stack was kept (Django 5 + DRF + MySQL, Angular 19
standalone). No rewrite: working code was reused and reshaped.

---

## What the project looked like before

- **Backend** — Django 5 + DRF + MySQL with 7 apps:
  - `authentication`: JWT username/password login, **public registration**, roles
    `admin` / `manager` / `guest`, no PIN.
  - `products`: Category tree, Color, Size, Product (unique barcode),
    ProductVariant (color × size, sku, barcode, stock). **No Brand entity existed.**
  - `inventory`: StockItem batches (vendor, cost, dates) + StockAdjustment.
  - `sales`: Sale with `cash` / `credit` / `installment`, SaleItem, ReportLab PDF
    receipt. Cash sales assumed `paid == total` and never computed change.
  - `vendors`, `customers` (credit limit, InstallmentPlan, InstallmentPayment),
    `ai_analysis` (Groq).
- **Frontend** — Angular 19 + Material, English-only, no i18n: dashboard, POS,
  products, categories, colors, sizes, inventory, vendors, customers, sales,
  reports, settings.
- **No tests** (0 test files). POS did not handle received cash or change.

---

## What was changed

### Backend

- **Roles** rewritten to `owner` / `manager` / `cashier` (legacy `admin` → `owner`,
  `guest` → `cashier` via `authentication/migrations/0002_map_legacy_roles.py`).
  `User` gained `pin_hash`, `pin_failed_attempts`, `pin_locked_until`, `language`,
  a `display_name` helper and `can_view_financials`.
- **PIN login** (`POST /api/auth/login/pin/`): PIN is hashed with Django's
  password hasher (`set_pin` / `check_pin` — never stored or logged in plaintext),
  with attempt counting and a temporary lockout after `PIN_MAX_ATTEMPTS`
  failures (`PIN_LOCKOUT_SECONDS`). Owner can set/reset an employee's PIN.
- **Public registration removed** — employees are created only by owner/manager
  through `POST /api/auth/users/`.
- **Role permissions enforced on the API** (`authentication/permissions.py`),
  not just hidden in the UI. Cost price, unit cost, margin, profit and inventory
  valuation are stripped from serializers / blocked for non-owners.
- **Products**: Category is the only classification; low-stock threshold per
  product; barcode auto-generation when omitted; variant-level barcode + stock.
  Colors/Sizes remain as *data* used by variants (no dedicated pages).
- **Customers simplified**: credit limit, InstallmentPlan/InstallmentPayment
  removed — a plain customer record remains.
- **Inventory**: new `StockReceipt` (+ items) for goods intake, and a full
  `StockMovement` audit trail (purchase / sale / return / adjustment / inventory).
  `inventory/services.py` centralises all stock changes so stock can never be
  edited silently.
- **Sales**: payment methods `cash` / `card` / `mixed`; cash received + change
  (`resolve_payment`), sequential receipt numbers, atomic checkout with row locks
  (`select_for_update` inside the transaction), returns (`SaleReturn`) that put
  stock back and update the sale status without deleting it, and a
  role-aware `/api/sales/dashboard/`.
- **New `finance` app**: INCOME/EXPENSE entries with category, comment, date,
  created_by; owner-only financial summary (revenue, COGS, gross, expenses, net).
- **New `reports` app**: Excel (`.xlsx`) and CSV (UTF-8 BOM for Excel) exports for
  sales, stock, receipts, finance and the owner financial report.
- **New `audit` app**: WHO / WHAT / WHEN log for user creation, PIN change,
  product/price changes, receipts, adjustments, sales, returns, finance and
  deactivations. Secrets/PINs are never written to the log.
- **Seed command** `seed_data` creates starter categories (no hardcoded list in
  code), colours and sizes; `create_admin` creates the owner account (idempotent).

### Frontend

- **i18n** with a lightweight custom `TranslationService` + `TranslatePipe`
  (no new dependency), languages **RU / UZ** only. Selected language is persisted
  per user. English UI removed.
- **PIN login screen** — numeric keypad, no username field.
- **POS** rebuilt: single search field (`nom yoki shtrix-kod`), name/barcode
  search, scanner-friendly input, cart with size/colour/qty/price/line total,
  cash / card / mixed payment, received amount and live change; stock limits
  enforced server-side.
- **New/updated screens**: dashboard (period selector, revenue, sales count, units,
  cash/card split, average ticket, top products, simple chart, low stock),
  products, product form, categories, stock, receipts (kirim), sales history +
  detail + receipt print + return, finance (income/expense), reports + exports,
  employees (owner only), settings.
- **Sidebar** is compact and role-filtered: a cashier sees only POS, sales and
  settings.
- Removed unused feature folders (colors, sizes, customers, vendors, register,
  and the old reporting/analysis pages) and the dead code around them.

---

## UI/UX redesign

The frontend was restyled into a modern retail SaaS interface without touching
business logic or changing the framework (Angular 19 + Material kept).

- **Design system** (`styles.scss`): CSS custom-property tokens for colour,
  spacing, radius and shadow; unified buttons, cards, badges, forms, tables
  (sticky header + hover), dropdown menus, modal/drawer, tabs, pagination,
  skeletons, empty states and toasts. All screens share the same classes, so the
  whole app reads as one product.
- **Dark mode** — light / dark / system, persisted in `localStorage`, applied via
  a single `data-theme` attribute by `ThemeService` and exposed in the header and
  profile menu.
- **App shell** — collapsible sidebar (icons-only when collapsed, animated,
  persisted), active-item highlight, and a header with the current page title,
  global product search, theme toggle, RU/UZ switcher and a profile dropdown
  (settings, theme, logout).
- **POS** — the primary screen: large scanner-friendly search, skeleton loading,
  product cards (name, category, colour/size, price, stock badge), cart with
  quantity controls and row highlight animation, a payment modal
  (cash / card / mixed) with prominent change and quick-cash buttons, a success
  state with the receipt number, and keyboard shortcuts (`F2` search, `Enter`
  scan/add, `F4` pay, `Esc` close).
- **Dashboard** — KPI cards with icons and honest period-over-period trends
  (computed from the previous period; shown only when reliable), owner-only
  profit cards, sales chart, cash-vs-card split, top products, recent sales,
  low stock and recent expenses.
- **Tables** — search/filters, sticky headers, status badges with text, and a
  per-row actions menu (`⋯`) instead of a row of buttons.
- **Feedback** — a global `ToastService` + host replaces ad-hoc snackbars, and a
  promise-based `ConfirmService` modal replaces `window.confirm()`. Forms show
  loading states and guard against double submits.
- **Empty states** on products, categories, finance, employees, sales, stock and
  the dashboard instead of blank tables.

## Admin panel

- **PIN login** — the Django admin no longer shows a username/password form. A
  custom view (`apps/authentication/admin_login.py`) authenticates active *staff*
  accounts by PIN, reusing the same database-backed throttling and audit logging
  as the API. The standard password login still works for the API, but `/admin/`
  is PIN-only.
- **Language** — Uzbek + Russian. `LocaleMiddleware` + `LANGUAGES` are enabled, an
  admin language switcher was added to the header (`templates/admin/base_site.html`),
  and after PIN login the admin opens in the employee's saved language. Admin
  chrome (buttons, filters, pagination) is translated by Django.
- **Translated sections & models** — every app section and model name (Users,
  Products, Sales, Stock movements, …) is translated via `locale/{uz,ru}`
  (`compilemessages` runs in the image build), so the whole panel is consistent,
  not a mix of English and Uzbek.
- **Decluttered** — the technical JWT token tables (Blacklisted/Outstanding
  tokens) are hidden, since they mean nothing to a shop owner.
- **Branding** — admin header shows the shop name.

## What was removed (and why)

| Removed | Reason |
|---|---|
| Public registration | Employees are created only by owner/admin. |
| `admin` / `guest` roles | Replaced by `owner` / `manager` / `cashier`. |
| Credit limit, InstallmentPlan, InstallmentPayment | Shop sells for cash/card only. |
| Colors & Sizes pages | Managed implicitly through product variants. |
| Customers & Vendors UI pages | Not needed for daily shop work. |
| English language | UI is RU/UZ only. |
| Ad-hoc inline styling | Replaced by the shared design system. |
| Browser `alert`/`confirm`, Material snackbars | Replaced by the confirm modal and toasts. |
| Old AI/analysis & reporting frontend pages | Replaced by finance + reports. |
| Old migrations history | Replaced with a clean, self-consistent set (see Database). |

`Brand` did **not** exist in the original project, so nothing was removed for it.
The `vendors` and `ai_analysis` backend apps were kept (they are wired but no
longer exposed in the UI) — they can be deleted later if unused.

---

## Database

Models added: `audit.AuditLog`, `inventory.StockReceipt` + `StockReceiptItem`,
`inventory.StockMovement`, `sales.SaleReturn` + `SaleReturnItem`,
`finance.FinanceEntry`.

Models changed: `authentication.User` (roles, PIN fields, language),
`sales.Sale` (payment methods, cash/card/received/change, statuses),
`products.Product` / `ProductVariant` (low-stock threshold, barcode handling),
`customers.Customer` (credit/installment fields dropped).

The previous migration history referenced models that no longer exist, so the
app migration folders were regenerated as a clean, self-consistent set, plus
`authentication/0002_map_legacy_roles.py` which safely maps existing role values
onto the new ones (existing users are not deleted).

Indexes/constraints: unique barcode on product and variant, unique user PIN
hash lookup via `username`, unique sequential sale/receipt numbers.

---

## Permissions

| Area | Owner | Manager | Cashier |
|---|---|---|---|
| POS / sales | ✅ | ✅ | ✅ (own sales) |
| Products / categories / stock / receipts | ✅ | ✅ | ❌ |
| Returns | ✅ | ✅ | ❌ |
| Income / expense (view) | ✅ | ✅ (operational) | ❌ |
| Revenue, cash/card, sales count | ✅ | ✅ | own shift only |
| Cost price, margin, gross/net profit, valuation | ✅ | ❌ (blocked by API) | ❌ |
| Employees, PIN management | ✅ | ❌ | ❌ |
| Reports / exports | ✅ | operational | ❌ |

Enforcement is on the backend (serializers + permissions); the frontend merely
mirrors it.

---

## POS flow

1. Cashier logs in with a PIN.
2. Types a product name or scans/enters a barcode — matching variants appear.
3. Selecting a variant adds it to the cart (size, colour, qty, price, line total).
4. Choose **cash**, **card** or **mixed**; for cash the system computes
   `change = received − total` and refuses payment if received < total.
5. On confirm, atomically: create `Sale` + `SaleItem`s, decrement stock via a
   `StockMovement`, record cashier/time/payment, create the receipt.
6. Receipt can be shown, printed (thermal 80 mm PDF) and re-opened/re-printed
   later from sales history.

---

## Reports

Excel (`.xlsx`) and CSV (Excel-friendly, UTF-8 BOM): sales, stock on hand,
receipts, income/expenses and the owner financial report. Files are named
clearly, e.g. `sales_2026-09.xlsx`, `stock_2026-09-30.xlsx`,
`expenses_2026-09.xlsx`. Owner picks a period (today / yesterday / week / month /
custom range).

---

## Tests

- **Unit tests** — `python manage.py test apps`: **115 tests, OK** (4 of them cover
the admin PIN login). They cover
  the 28 required scenarios: PIN login + rejection + hashing + lockout, no public
  registration, RU/UZ, category CRUD, product without Brand, unique barcode,
  search by name/barcode, sale reduces stock, overselling blocked, cash change,
  sale history, receipt, manager/cashier API restrictions, expense/income,
  goods receipt, StockMovement, return, Excel/CSV export, dashboard.
- **End-to-end** — `python3 verify_e2e.py` against the running Docker stack
  (through nginx): **46 checks, ALL PASSED**.

An E2E run caught a real bug (row locks used outside a transaction, so checkout
failed over HTTP while unit tests passed) — the checkout was moved fully inside
`transaction.atomic()`.

---

## Remaining issues / manual checks

- PIN lockout state is stored on the user row; a shared cache (Redis) would be
  better at scale but is unnecessary for one shop.
- Receipt output is PDF tuned for 80 mm thermal printers; verify against the
  physical printer model in use.
- The `vendors` and `ai_analysis` backend apps are still installed but have no
  UI — remove if they stay unused.
- `DEBUG=True` and a default `SECRET_KEY` are used for local Docker only; set
  real values before exposing the app on a server (`ALLOWED_HOSTS`, HTTPS).
- Frontend UI was verified via the API/E2E layer; run a manual click-through of
  POS printing and returns on the target machine.
