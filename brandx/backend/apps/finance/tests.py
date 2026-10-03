"""Web-level finance tests: income/expense forms, owner-only deletion and
period filters.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.authentication.models import User
from apps.finance.models import FinanceEntry
from apps.stores.models import Store


class FinanceWebBase(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name='Fin Store', code='FIN')
        self.owner = self._make_user('fin-owner', 'owner', '1234')
        self.manager = self._make_user('fin-manager', 'manager', '2345')
        self._login('1234')

    def _make_user(self, username, role, pin):
        user = User(username=username, first_name=username.title(), role=role,
                    store=self.store, language='uz')
        user.set_unusable_password()
        user.set_pin(pin)
        user.save()
        return user

    def _login(self, pin):
        response = self.client.post(reverse('web:store-login', kwargs={'code': 'FIN'}),
                                    {'pin': pin, 'store_code': 'FIN'})
        self.assertEqual(response.status_code, 302)

    def _create_entry(self, **overrides):
        data = {'entry_type': 'income', 'amount': '500.00', 'category': 'Savdo',
                'entry_date': '2026-10-01', 'comment': 'test'}
        data.update(overrides)
        return self.client.post(reverse('web:finance-save'), data)


class FinanceEntryTests(FinanceWebBase):
    def test_owner_creates_income_entry(self):
        response = self._create_entry()
        self.assertEqual(response.status_code, 302)
        entry = FinanceEntry.objects.get()
        self.assertEqual(entry.store, self.store)
        self.assertEqual(entry.entry_type, FinanceEntry.TYPE_INCOME)
        self.assertEqual(entry.amount, Decimal('500.00'))
        self.assertEqual(entry.created_by, self.owner)
        self.assertEqual(entry.entry_date, date(2026, 10, 1))

    def test_expense_entry(self):
        response = self._create_entry(entry_type='expense', amount='120.50',
                                      category='Transport')
        self.assertEqual(response.status_code, 302)
        entry = FinanceEntry.objects.get()
        self.assertEqual(entry.entry_type, FinanceEntry.TYPE_EXPENSE)
        self.assertEqual(entry.amount, Decimal('120.50'))

    def test_invalid_amount_rejected(self):
        response = self._create_entry(amount='not-a-number')
        self.assertEqual(response.status_code, 200)  # re-rendered with error message
        self.assertFalse(FinanceEntry.objects.exists())

    def test_negative_amount_rejected(self):
        response = self._create_entry(amount='-5')
        self.assertEqual(response.status_code, 200)  # re-rendered with error message
        self.assertFalse(FinanceEntry.objects.exists())

    def test_period_and_type_filters(self):
        self._create_entry(entry_type='income', amount='100',
                           entry_date='2026-10-01', comment='kirim-izoh')
        self._create_entry(entry_type='expense', amount='30', category='Transport',
                           entry_date='2026-09-15', comment='chiqim-izoh')

        response = self.client.get(reverse('web:finance'), {'entry_type': 'expense'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'chiqim-izoh')
        self.assertNotContains(response, 'kirim-izoh')

    def test_owner_can_delete_entry(self):
        self._create_entry()
        entry = FinanceEntry.objects.get()
        response = self.client.post(reverse('web:finance-delete', kwargs={'pk': entry.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FinanceEntry.objects.exists())

    def test_manager_cannot_delete_entry(self):
        self._create_entry()
        entry = FinanceEntry.objects.get()
        self.client.logout()
        self._login('2345')
        response = self.client.post(reverse('web:finance-delete', kwargs={'pk': entry.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(FinanceEntry.objects.filter(pk=entry.pk).exists())
