# Multi-store architecture audit — 2026-10-01

> **2026-10-03 update:** the DRF/JWT API layer and the Angular 19 frontend have
> since been removed; the UI is now fully server-rendered Django templates with
> session auth (see README.md). This document is kept as a historical record —
> references to DRF, JWT and Angular below describe the earlier architecture.

## Status and agreed decisions

> **Implemented & verified 2026-10-01** (see IMPLEMENTATION_REPORT.md): Store
> schema + BrandX backfill, PostgreSQL primary, platform panel, store-link login,
> tenant scoping, product matrix/simple flows, statistics/refund corrections,
> 145 tests (PG + SQLite), 24/24 live smoke checks and a MySQL → PostgreSQL
> cutover rehearsal. The findings below are kept as the audit record.

This is an incremental migration, not a rewrite. The deployed application remains
single-store until tenant enforcement and its tests are complete. Do not expose it
to multiple customers in the meantime.

User decisions:
- Preserve existing data in a **BrandX** legacy store.
- Store login uses **/store/<CODE>/login + PIN**; identical PINs may exist in
  different stores, but not for two active employees in the same store.
- Convert existing `admin` to `platform_admin`. Preserve its historical cashier
  references. A separate BrandX owner must be provisioned; do not guess credentials.

## Existing implementation

- Django 5.0.4 / DRF / SimpleJWT, Python 3.11, Angular 19 standalone.
- MySQL 8 via mysqlclient, SQLite for unit tests, Docker Compose + gunicorn/nginx.
- Apps: authentication, products, inventory, sales, finance, reports, audit,
  customers, vendors, optional AI analysis. No Store or Brand entity exists.
- Stock source of truth: ProductVariant.stock_quantity. StockMovement records
  receipts, sales, returns and adjustments. Product serializers also write stock
  directly, bypassing the movement trail.
- User roles: owner / manager / cashier. PIN hashes use Django password hashing;
  IP attempt throttling is database-backed. Current PIN discovery and uniqueness
  are **global**, so PIN-only login cannot disambiguate stores.
- JWT authenticates users but does not currently enforce store status. Refresh
  tokens, password login and framework-admin login also need explicit review.
- `create_admin` overwrites credentials/role on every container startup. Owners
  created by that command are staff and superusers; ordinary owners must not have
  technical-admin access in the commercial platform.
- Product form manually adds one variant row at a time. Nullable size/color
  already supports simple products in the model, but there is no dedicated simple
  workflow, matrix, inline category modal or duplication flow.
- Existing dashboard draws CSS bars, not a line chart. Supporting sales/expense
  panels ignore the selected date filter. Frontend UTC date formatting introduces
  local-date boundary/comparison errors.

## Database compatibility review

Search of backend Python/migrations found no application raw SQL, RunSQL,
MySQL-specific functions, custom auto-increment columns or vendor-specific model
fields. Existing migrations use Django schema operations plus a role RunPython
migration. These must remain intact; do not regenerate initial migrations.

- MySQL-specific settings: charset utf8mb4 and SET sql_mode; driver and startup
  connection loop; Docker image, port, healthcheck and volume.
- BigAutoField: PostgreSQL identities/sequences; imports retaining IDs require a
  Django-generated sequence reset before new writes.
- Decimal fields: preserve exact values, never convert accounting amounts to float.
- JSONField: maps to PostgreSQL jsonb; verify audit details after transfer.
- Boolean fields: portable; preserve actual booleans in serialized transfer.
- USE_TZ=True; source/target must use matching Django timezone interpretation.
  Preserve timestamps, compare serialized values and test midnight boundaries.
- Global unique keys: category/color names, size name+type, product barcode,
  variant barcode/SKU, sale/stock-receipt numbers, printed receipt number.
  Convert appropriate constraints to store scope in **new** migrations.
- Existing variant (product,color,size) uniqueness permits multiple NULL attribute
  combinations. Decide/test one active simple variant and duplicate combinations
  explicitly; do not rely on a nullable unique_together alone.
- MySQL case-insensitive collation differs from PostgreSQL text comparisons.
  Store codes should be normalized; names/barcode rules need explicit validation
  and tests rather than relying on collation.
- POS select_for_update + nullable color/size outer joins fails on PostgreSQL
  unless locking is limited to the variant table (`of=('self',)`).
- Sale and stock document numbering uses max+1 / locking last row. It races for
  empty tables and concurrent documents. Introduce per-store counters locked
  inside transactions, not global last-row locking.

PostgreSQL 17 is a supported stable major (through November 2029); use current
minor updates. Django 5.0 is no longer a supported Django release in October 2026.
A tested upgrade to Django 5.2 LTS is a production-hardening requirement, not a
claim that the current dependency pin is production-supported.

## Security findings to address before multi-store deployment

- All major catalog, finance, vendor/customer, inventory, audit and export
  querysets are global. Cashier sale filtering alone is not tenant isolation.
- POS custom search/barcode/low-stock actions bypass view queryset filtering.
- Serializer related-field querysets are global; scoping list/detail endpoints
  alone will not prevent cross-store foreign-key injection.
- Sales receive raw customer/variant IDs and services fetch them globally.
- Sales/statistics/export/AI services need explicit store parameters with no
  global fallback. Optional AI sends collected business context to an external
  provider; do not inadvertently collect another store's information.
- Stock receipt serializers and exports currently expose purchase cost to
  managers. Cost masking mostly handles representations, not incoming writes.
- Platform roles must be disallowed in employee create/update, and platform
  accounts must not gain implicit access to shop financial/export APIs.
- Existing technical Django admin requires independent protection; a commercial
  owner must not be able to bypass API isolation there.

## POS and accounting findings

- Historical SaleItem.unit_cost/name/size/color snapshots already exist and must
  be preserved (do not calculate past COGS from current catalog prices).
- Fully refunded sales are excluded from COUNTED_STATUSES but returns are still
  subtracted: net revenue/COGS can become incorrectly negative.
- Returns use undiscounted unit_price, ignoring line and sale discounts; duplicate
  returned lines and concurrent returns can over-refund because validation is
  outside locking. Cancellation also needs locked state validation.
- Units sold and top products ignore returns. Top products group by name rather
  than stable product identity, and line totals ignore sale-wide discount.
- Mixed sale payment components are stored correctly, but refunds have no explicit
  cash/card allocation. Define and persist refund components for reliable net
  payment statistics; do not pretend old records contain this information.
- Existing net profit includes other income. Target primary net profit is gross
  profit - expenses; show other income separately or explicitly label an alternate
  net result. Average receipt must have a documented net/gross basis.
- Range filtering currently uses __date transforms; PostgreSQL date+store queries
  should use aware half-open timestamps to benefit from composite indexes.

## Intended tenant design (not yet implemented)

- Shared PostgreSQL database, explicit store FK for root tenant entities, child
  scope through parents where appropriate. No schema-per-store complexity.
- Store-owned user requires a store; platform_admin is global. Preserve historical
  relationships even if a cashier is promoted globally.
- New migrations create BrandX, backfill roots, validate parent relationships,
  then enforce non-null/unique/index constraints. Never assign every new record
  to a default store as a fallback.
- All request querysets and writable related fields derive store from authenticated
  user; client store_id is never authoritative.
- Service entry points require tenant context and validate all related inputs.
- Store deactivation checked on every authenticated request and login/refresh;
  tokens already issued must not bypass it. Reactivation restores access.
- /platform application UI + separate permission-gated APIs expose store management
  and platform counts, not broad customer-financial dumps.
- Store+first owner creation and numbering/checkout/return/receipt operations atomic.
- Barcodes unique within a store, including product/variant lookup namespace.
  Cross-table collisions require deliberate race-safe enforcement, not two
  independent unique constraints alone.
- Audit events carry explicit store context, including global admin actions.

## Baseline verification

2026-10-01: ran `python manage.py test apps --verbosity=1` using an isolated
SQLite database in Docker: **115 tests passed**, no Django system-check issues.
This does **not** verify PostgreSQL, concurrency or tenant isolation. Existing
E2E script writes data and expects seeded development state; do not run it against
customer data. It must be adapted for isolated store fixtures before reuse.

## Acceptance gates / pending work

1. PostgreSQL configuration + protected export/import with counts, content hashes,
   relationships and sequence validation. Preserve MySQL source and media backup.
2. Store schema/backfill + user roles/login + fail-closed tenant infrastructure.
3. Platform API/UI and store-bound employee management.
4. Mandatory two-store read/write IDOR, related-ID injection, barcode, exports,
   statistics, deactivation, old JWT and refresh tests, running on PostgreSQL.
5. Product matrix/simple/duplicate/category/scanner workflows with atomic writes
   and audited stock movements.
6. POS/concurrency/refund verification, statistics tests before chart changes.
7. Shared range + backend granularity + line chart, store receipt/settings/exports.
8. RU/UZ and role UI verification, reference-proven cleanup, final documentation.

No code or dependencies should be removed merely because there is no sidebar
link. Vendors are actively used by stock receipts; customers may be used by POS.
