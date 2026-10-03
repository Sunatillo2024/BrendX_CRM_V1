#!/usr/bin/env python3
"""Smoke test for the BrandX server-rendered stack (stdlib only).

Run against a freshly provisioned stack:
    python3 verify_multistore.py
Base URL: http://localhost:8000 — Django now serves the UI, exports and admin
directly (the Angular/nginx container no longer exists).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.cookiejar import CookieJar

BASE = 'http://localhost:8000'
PLATFORM_PIN = os.environ.get('PLATFORM_PIN', '0000')
STORE_PIN = os.environ.get('STORE_PIN', '0808')
SUFFIX = uuid.uuid4().hex[:6]  # rerun-safe barcodes

results = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """Tiny session client: cookie jar, CSRF token, no-redirect requests."""

    def __init__(self):
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), NoRedirect())

    def csrf(self):
        for cookie in self.jar:
            if cookie.name == 'csrftoken':
                return cookie.value
        return ''

    def request(self, method, path, data=None, form=None, raw=False):
        url = BASE + path
        body = None
        headers = {'Referer': BASE + path}
        if form is not None:
            form = dict(form, csrfmiddlewaretoken=self.csrf())
            body = urllib.parse.urlencode(form).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        elif data is not None:
            body = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        token = self.csrf()
        if token:
            headers['X-CSRFToken'] = token
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=30) as res:
                payload = res.read()
                location = res.headers.get('Location', '')
                return res.status, location, (payload if raw else payload.decode('utf-8', 'ignore'))
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            location = exc.headers.get('Location', '')
            return exc.code, location, (payload if raw else payload.decode('utf-8', 'ignore'))


def check(name, ok, extra=''):
    results.append((name, bool(ok), extra))
    print(('PASS  ' if ok else 'FAIL  ') + name + (f'  {extra}' if extra else ''))


def main():
    platform = Client()

    # 1. Web app is served
    status, loc, _ = platform.request('GET', '/')
    check('web app responds', status in (200, 302), f'{status} -> {loc}')

    # 2. Platform login page + PIN login (session + CSRF, no JWT)
    status, _, html = platform.request('GET', '/platform/login/')
    cookies = {c.name for c in platform.jar}
    check('platform login page + CSRF cookie', status == 200 and 'csrftoken' in cookies, str(status))
    status, loc, _ = platform.request('POST', '/platform/login/', form={'pin': PLATFORM_PIN})
    check('platform PIN login', status == 302 and loc.endswith('/platform/'), f'{status} -> {loc}')
    status, _, html = platform.request('GET', '/platform/')
    check('platform dashboard renders', status == 200, str(status))

    # 3. Create two isolated stores, each with its own owner (transactional form)
    store_ids = {}
    for name, code in [('NewMax', 'NEWMAX'), ('Fashion KG', 'FASHION')]:
        status, loc, _ = platform.request('POST', '/platform/stores/create/', form={
            'name': name, 'code': code, 'owner_name': code.title(),
            'owner_pin': STORE_PIN, 'owner_language': 'ru'})
        if status == 302:
            match = re.search(r'/platform/stores/(\d+)/', loc)
            if match:
                store_ids[code] = int(match.group(1))
        if code not in store_ids:  # rerun-safe: store may already exist
            _, _, payload = platform.request('GET', f'/platform/stores/?search={code}')
            try:
                rows = json.loads(payload)
                if isinstance(rows, dict):
                    rows = rows.get('results') or []
                store_ids[code] = rows[0]['id'] if rows else None
            except ValueError:
                store_ids[code] = None
        check(f'store {code} provisioned (store + owner transaction)',
              status == 302 and store_ids.get(code), str(status))

    # 4. Owners log in through their store link with the SAME pin
    owner = {}
    for code in store_ids:
        client = Client()
        client.request('GET', f'/store/{code}/login/')
        status, loc, _ = client.request('POST', f'/store/{code}/login/',
                                        form={'pin': STORE_PIN, 'store_code': code})
        check(f'{code} owner login via /store/{code}/login', status == 302, f'{status} -> {loc}')
        owner[code] = client

    owner_a, owner_b = owner.get('NEWMAX'), owner.get('FASHION')
    if owner_a is None or owner_b is None:
        return finish()

    # 5. Owner must not reach the platform panel
    status, _, _ = owner_a.request('GET', '/platform/')
    check('owner blocked from platform panel', status in (302, 403), str(status))

    # 6. Owner A creates a category + simple product with stock (web forms + CSRF)
    status, _, _ = owner_a.request('POST', '/categories/save/', form={
        'name': f'Футболка-{SUFFIX}', 'description': 'smoke', 'is_active': 'on'})
    check('owner creates category in own store', status == 302, str(status))
    barcode = f'smoke-newmax-{SUFFIX}'
    formset = {'variants-TOTAL_FORMS': '1', 'variants-INITIAL_FORMS': '0',
               'variants-MIN_NUM_FORMS': '0', 'variants-MAX_NUM_FORMS': '1000'}
    status, _, _ = owner_a.request('POST', '/products/new/', form={
        'name': 'Футболка Classic', 'barcode': barcode,
        'base_selling_price': '2300', 'base_cost_price': '1500', 'is_active': 'on',
        'low_stock_threshold': '3',
        'variants-0-stock_quantity': '5', 'variants-0-is_active': 'on', **formset})
    check('owner creates simple product with stock movement', status == 302, str(status))

    # 7. The same barcode is allowed in the other store (store-aware uniqueness)
    status, _, _ = owner_b.request('POST', '/products/new/', form={
        'name': 'Футболка Classic', 'barcode': barcode,
        'base_selling_price': '2300', 'is_active': 'on',
        'low_stock_threshold': '3',
        'variants-0-stock_quantity': '3', 'variants-0-is_active': 'on', **formset})
    check('duplicate barcode allowed across stores', status == 302, str(status))

    # 8. Cross-store read must 404
    _, _, rows_raw = owner_b.request('GET', f'/pos/search/?q={barcode}')
    try:
        rows = json.loads(rows_raw).get('results', [])
        product_b_id = rows[0]['product_id'] if rows else None
    except ValueError:
        product_b_id = None
    if product_b_id:
        status, _, _ = owner_a.request('GET', f'/products/{product_b_id}/edit/')
        check('cross-store product edit is 404', status == 404, str(status))

    # 9. POS checkout in store A (JSON + CSRF header, same as the POS page)
    _, _, rows_raw = owner_a.request('GET', f'/pos/search/?q={barcode}')
    try:
        variant_id = json.loads(rows_raw)['results'][0]['id']
    except (ValueError, KeyError, IndexError):
        variant_id = None
    status, _, payload = owner_a.request('POST', '/pos/checkout/', data={
        'payment_method': 'cash', 'received_amount': '5000',
        'items': [{'product_variant_id': variant_id, 'quantity': 1, 'unit_price': '2300'}]})
    sale_id = None
    try:
        payload = json.loads(payload)
        sale_id = payload.get('id')
        check('POS checkout in NewMax', status == 200, f'{status} {payload}')
        check('change calculated', str(payload.get('change')) == '2700.00',
              str(payload.get('change')))
    except ValueError:
        check('POS checkout in NewMax', False, str(status))

    # 10. Store-branded receipt PDF
    if sale_id:
        status, _, pdf = owner_a.request('GET', f'/sales/{sale_id}/receipt.pdf', raw=True)
        check('store receipt PDF', status == 200 and pdf[:4] == b'%PDF', str(status))

    # 11. Export from store A must not contain store B rows
    status, _, csv_text = owner_a.request('GET', '/reports/export/sales/?period=all&fmt=csv&lang=ru')
    check('export scoped to own store', status == 200 and 'Fashion KG' not in csv_text, str(status))

    # 12. Both owner dashboards render
    status_a, _, _ = owner_a.request('GET', '/dashboard/')
    status_b, _, _ = owner_b.request('GET', '/dashboard/')
    check('owner dashboards render', status_a == 200 and status_b == 200,
          f'A={status_a} B={status_b}')

    # 13. Store deactivation blocks the session and login; reactivation restores it
    newmax_id = store_ids.get('NEWMAX')
    if newmax_id:
        status, _, _ = platform.request('POST', f'/platform/stores/{newmax_id}/update/',
                                        form={'toggle': '1'})
        check('platform deactivates store', status == 302, str(status))
        status, _, _ = owner_a.request('GET', '/products/')
        check('deactivated store session blocked', status in (302, 403), str(status))
        fresh = Client()
        fresh.request('GET', '/store/NEWMAX/login/')
        status, _, _ = fresh.request('POST', '/store/NEWMAX/login/',
                                     form={'pin': STORE_PIN, 'store_code': 'NEWMAX'})
        check('deactivated store login rejected', status in (400, 403), str(status))
        status, _, _ = platform.request('POST', f'/platform/stores/{newmax_id}/update/',
                                        form={'toggle': '1'})
        check('platform reactivates store', status == 302, str(status))
        fresh = Client()
        fresh.request('GET', '/store/NEWMAX/login/')
        status, _, _ = fresh.request('POST', '/store/NEWMAX/login/',
                                     form={'pin': STORE_PIN, 'store_code': 'NEWMAX'})
        check('reactivation restores access', status == 302, str(status))

    # 14. Technical Django admin keeps its PIN pad (fresh session: an already
    # logged-in platform admin is correctly redirected into the admin).
    fresh_admin = Client()
    status, _, html = fresh_admin.request('GET', '/admin/login/')
    check('admin PIN login page', status == 200 and 'name="pin"' in html, str(status))

    return finish()


def finish():
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print('FAILED: ' + ', '.join(r[0] for r in failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
