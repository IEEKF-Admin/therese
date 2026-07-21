"""Unit tests for employee list contract display / expiry warnings."""

from datetime import date, timedelta

from django.test import TestCase

from apps.hr.employee_list_helpers import (
    contract_needs_expiry_warning,
    display_contract_valid_until,
    has_seamless_followup,
)
from apps.hr.models import Contract, Employee
from apps.hr.validity import select_contract_as_of


class EmployeeListHelperTests(TestCase):
    def setUp(self):
        self.today = date(2026, 7, 21)
        self.emp = Employee.objects.create(
            employee_number='L1', first_name='List', last_name='Test',
        )

    def _contract(self, **kwargs):
        defaults = {
            'employee': self.emp,
            'weekly_hours': 40,
            'valid_from': date(2020, 1, 1),
            'is_active': True,
        }
        defaults.update(kwargs)
        return Contract.objects.create(**defaults)

    def test_open_ended_no_warning(self):
        c = self._contract(valid_until=None)
        self.assertFalse(contract_needs_expiry_warning(c, [c], as_of=self.today))

    def test_expiring_without_followup_warns(self):
        c = self._contract(valid_until=self.today + timedelta(days=30))
        self.assertTrue(contract_needs_expiry_warning(c, [c], as_of=self.today))

    def test_seamless_followup_no_warning(self):
        c = self._contract(valid_until=self.today + timedelta(days=20))
        # Future successor may be inactive until it becomes current (DB: max one active)
        follow = self._contract(
            valid_from=c.valid_until + timedelta(days=1),
            valid_until=None,
            is_active=False,
        )
        self.assertTrue(has_seamless_followup(c, [c, follow]))
        self.assertFalse(contract_needs_expiry_warning(c, [c, follow], as_of=self.today))

    def test_gapped_followup_warns(self):
        c = self._contract(valid_until=self.today + timedelta(days=20))
        later = self._contract(
            valid_from=c.valid_until + timedelta(days=30),
            valid_until=None,
            is_active=False,
        )
        self.assertFalse(has_seamless_followup(c, [c, later]))
        self.assertTrue(contract_needs_expiry_warning(c, [c, later], as_of=self.today))

    def test_no_current_contract_warns(self):
        self.assertTrue(contract_needs_expiry_warning(None, [], as_of=self.today))

    def test_display_valid_until_current(self):
        end = self.today + timedelta(days=10)
        c = self._contract(valid_until=end)
        info = display_contract_valid_until(c, [c], as_of=self.today)
        self.assertEqual(info['date'], end)
        self.assertFalse(info['open_ended'])

    def test_display_falls_back_to_future(self):
        future_from = self.today + timedelta(days=60)
        future_until = self.today + timedelta(days=400)
        # Past contract only — no open soft contract
        self._contract(
            valid_from=date(2020, 1, 1),
            valid_until=self.today - timedelta(days=10),
            is_active=False,
        )
        future = self._contract(
            valid_from=future_from,
            valid_until=future_until,
            is_active=False,
        )
        current = select_contract_as_of(self.emp.contracts.all(), self.today)
        self.assertIsNone(current)
        info = display_contract_valid_until(None, list(self.emp.contracts.all()), as_of=self.today)
        self.assertEqual(info['from_date'], future_from)
        self.assertEqual(info['date'], future_until)
