"""Soft temporal resolution for contracts and funding allocations."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.finances.models import CostCenter, WBSElement
from apps.hr.models import Contract, Employee, FundingAllocation
from apps.hr.validity import dedupe_allocations_as_of, select_contract_as_of


class ContractSoftSelectTests(TestCase):
    def setUp(self):
        self.emp = Employee.objects.create(
            employee_number='90001',
            first_name='Ada',
            last_name='Lovelace',
        )

    def test_latest_started_open_contract_wins(self):
        Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('3000.00'),
            valid_from=date(2024, 1, 1),
            valid_until=None,
        )
        newer = Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('20.00'),
            monthly_salary=Decimal('4000.00'),
            valid_from=date(2025, 6, 1),
            valid_until=None,
        )
        as_of = date(2026, 7, 1)
        picked = self.emp.get_contract_as_of(as_of)
        self.assertEqual(picked.pk, newer.pk)
        self.assertEqual(picked.monthly_salary, Decimal('4000.00'))

    def test_future_start_is_ignored(self):
        current = Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('3000.00'),
            valid_from=date(2024, 1, 1),
            valid_until=None,
        )
        Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('9999.00'),
            valid_from=date(2030, 1, 1),
            valid_until=None,
        )
        picked = self.emp.get_contract_as_of(date(2026, 7, 1))
        self.assertEqual(picked.pk, current.pk)

    def test_ended_contract_not_selected(self):
        Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('2000.00'),
            valid_from=date(2020, 1, 1),
            valid_until=date(2024, 12, 31),
        )
        active = Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('3500.00'),
            valid_from=date(2025, 1, 1),
            valid_until=None,
        )
        self.assertEqual(self.emp.get_contract_as_of(date(2026, 1, 1)).pk, active.pk)
        # Mid old contract: only the 2020–2024 row is open
        mid = self.emp.get_contract_as_of(date(2023, 6, 1))
        self.assertEqual(mid.monthly_salary, Decimal('2000.00'))
        # On last day of old contract it is still open
        old = select_contract_as_of(self.emp.contracts.all(), date(2024, 12, 31))
        self.assertEqual(old.monthly_salary, Decimal('2000.00'))
        # Day after old ends, only the new contract
        self.assertEqual(
            self.emp.get_contract_as_of(date(2025, 1, 1)).pk,
            active.pk,
        )


class FundingAllocationSoftSelectTests(TestCase):
    def setUp(self):
        self.cc = CostCenter.objects.create(cost_center='CC-VAL')
        self.wbs = WBSElement.objects.create(
            wbs_code='V-100.0001',
            title='Validity PSP',
            cost_center=self.cc,
            has_personnel_costs=True,
        )
        self.wbs_other = WBSElement.objects.create(
            wbs_code='V-100.0002',
            title='Other PSP',
            cost_center=self.cc,
            has_personnel_costs=True,
        )
        self.emp = Employee.objects.create(
            employee_number='90002',
            first_name='Grace',
            last_name='Hopper',
        )

    def test_latest_start_on_same_psp_wins(self):
        FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('30.00'),
            start_date=date(2024, 1, 1),
            end_date=None,
        )
        newer = FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('50.00'),
            start_date=date(2025, 3, 1),
            end_date=None,
        )
        picked = FundingAllocation.for_employee_wbs_as_of(
            self.emp, self.wbs, date(2026, 7, 1)
        )
        self.assertEqual(picked.pk, newer.pk)
        self.assertEqual(picked.workhours_percentage, Decimal('50.00'))

    def test_future_allocation_ignored(self):
        current = FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('40.00'),
            start_date=date(2024, 1, 1),
            end_date=None,
        )
        FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('99.00'),
            start_date=date(2030, 1, 1),
            end_date=None,
        )
        picked = self.emp.get_funding_allocation_as_of(
            wbs_element=self.wbs, as_of=date(2026, 1, 1)
        )
        self.assertEqual(picked.pk, current.pk)

    def test_different_psps_both_open(self):
        a = FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('50.00'),
            start_date=date(2024, 1, 1),
            end_date=None,
        )
        b = FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs_other,
            workhours_percentage=Decimal('50.00'),
            start_date=date(2024, 6, 1),
            end_date=None,
        )
        open_list = self.emp.get_open_funding_allocations_as_of(date(2026, 1, 1))
        pks = {x.pk for x in open_list}
        self.assertEqual(pks, {a.pk, b.pk})

    def test_dedupe_keeps_one_per_target(self):
        old = FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('20.00'),
            start_date=date(2023, 1, 1),
            end_date=None,
        )
        new = FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('80.00'),
            start_date=date(2025, 1, 1),
            end_date=None,
        )
        winners = dedupe_allocations_as_of([old, new], date(2026, 1, 1))
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].pk, new.pk)

    def test_end_before_start_rejected(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            FundingAllocation.objects.create(
                employee=self.emp,
                wbs_element=self.wbs,
                workhours_percentage=Decimal('50.00'),
                start_date=date(2025, 6, 1),
                end_date=date(2025, 1, 1),
            )


class IsActiveFieldTests(TestCase):
    def setUp(self):
        self.cc = CostCenter.objects.create(cost_center='CC-ACT')
        self.wbs = WBSElement.objects.create(
            wbs_code='A-100.0001',
            title='Active field PSP',
            cost_center=self.cc,
            has_personnel_costs=True,
        )
        self.emp = Employee.objects.create(
            employee_number='90003',
            first_name='Alan',
            last_name='Turing',
        )

    def test_past_end_auto_deactivates_contract(self):
        c = Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('3000.00'),
            valid_from=date(2020, 1, 1),
            valid_until=date(2021, 12, 31),
            is_active=True,
        )
        c.refresh_from_db()
        self.assertFalse(c.is_active)
        self.assertIsNone(self.emp.get_contract_as_of(date(2026, 1, 1)))

    def test_manual_inactive_excludes_from_soft_select(self):
        from django.utils import timezone

        today = timezone.now().date()
        inactive = Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('5000.00'),
            valid_from=date(2024, 1, 1),
            valid_until=None,
            is_active=False,
        )
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)
        # Current/as-of-today lookups respect is_active
        self.assertIsNone(self.emp.get_contract_as_of(today))

        active = Contract.objects.create(
            employee=self.emp,
            weekly_hours=Decimal('20.00'),
            monthly_salary=Decimal('2000.00'),
            valid_from=date(2023, 1, 1),
            valid_until=None,
            is_active=True,
        )
        picked = self.emp.get_contract_as_of(today)
        self.assertEqual(picked.pk, active.pk)

    def test_past_end_auto_deactivates_funding_allocation(self):
        fa = FundingAllocation.objects.create(
            employee=self.emp,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('50.00'),
            start_date=date(2020, 1, 1),
            end_date=date(2021, 6, 30),
            is_active=True,
        )
        fa.refresh_from_db()
        self.assertFalse(fa.is_active)
        self.assertIsNone(
            FundingAllocation.for_employee_wbs_as_of(self.emp, self.wbs, date(2026, 1, 1))
        )
