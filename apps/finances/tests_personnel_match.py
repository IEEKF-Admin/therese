"""Tests for Personalkosten → FundingAllocation import matching."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.core.models import GlobalSetting
from apps.finances.models import CostCenter, WBSElement
from apps.finances.report_import.personnel_match import (
    apply_personnel_decisions,
    build_personnel_checks,
    decision_key_for,
    tolerance_for_booking_date,
)
from apps.finances.report_import.service import merge_user_decisions
from apps.hr.models import Contract, Employee, FundingAllocation, SalarySupplement


class PersonnelMatchTests(TestCase):
    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'true_cost_multiplicator': Decimal('1.300'),
                'default_weekly_hours': Decimal('39.00'),
                'personnel_import_tolerance': Decimal('0.025'),
            },
        )
        self.cc = CostCenter.objects.create(cost_center='CC-PM')
        self.wbs = WBSElement.objects.create(
            wbs_code='D-100.0001',
            title='Personnel match PSP',
            cost_center=self.cc,
            has_personnel_costs=True,
        )
        self.employee = Employee.objects.create(
            employee_number='50001094',
            first_name='Kerstin',
            last_name='Hallmann',
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            valid_from=date(2025, 1, 1),
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('4000.00'),
            is_active=True,
        )
        self.alloc = FundingAllocation.objects.create(
            contract=self.contract,
            employee=self.employee,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('50.00'),
            start_date=date(2025, 1, 1),
            end_date=None,
            import_completed=False,
        )

    def _entry(self, personalnummer='50001094', amount='2600.00', booking='2026-06-01'):
        return {
            'personalnummer': personalnummer,
            'kostenart': '60003000',
            'personalkosten': amount,
            'belegdatum': booking,
            'buchungsdatum': booking,
            'buchungstext': 'HALLMANN KERSTIN Gehalt',
            'psp_code': 'D-100.0001.2',
            'parent_psp_code': 'D-100.0001',
            'source_filename': 't.xlsx',
        }

    def test_match_sets_import_completed(self):
        # expected = 4000 × 1.3 × 50% = 2600; Excel 2600 → match
        checks = build_personnel_checks(
            [self._entry('50001094', '2600.00')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]['status'], 'match')
        self.assertEqual(checks[0]['case'], 'a')
        self.assertEqual(checks[0]['expected_amount'], '2600.00')
        notes = apply_personnel_decisions(checks, {}, as_of=date(2026, 7, 1))
        self.alloc.refresh_from_db()
        self.assertTrue(self.alloc.import_completed)
        self.assertTrue(any('import_completed=Yes' in n for n in notes))

    def test_mismatch_adjust_salary(self):
        checks = build_personnel_checks(
            [self._entry('50001094', '3250.00')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(checks[0]['status'], 'mismatch')
        self.assertEqual(checks[0]['suggested_monthly_salary'], '5000.00')
        dkey = checks[0]['decision_key']
        notes = apply_personnel_decisions(
            checks,
            {dkey: 'adjust_salary'},
            as_of=date(2026, 7, 1),
        )
        self.alloc.refresh_from_db()
        self.assertTrue(self.alloc.import_completed)
        contract = self.employee.get_contract_as_of(date(2026, 7, 1))
        self.assertEqual(contract.monthly_salary, Decimal('5000.00'))
        self.assertTrue(any('base monthly salary (100%) set' in n for n in notes))

    def test_mismatch_ignore_keeps_flag(self):
        checks = build_personnel_checks(
            [self._entry('50001094', '3250.00')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        dkey = checks[0]['decision_key']
        apply_personnel_decisions(checks, {dkey: 'ignore'}, as_of=date(2026, 7, 1))
        self.alloc.refresh_from_db()
        self.assertFalse(self.alloc.import_completed)

    def test_no_employee_blocks_without_decision(self):
        checks = build_personnel_checks(
            [self._entry('99999999', '1000.00')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(checks[0]['status'], 'no_employee')
        self.assertEqual(checks[0]['case'], 'c')
        self.assertTrue(checks[0]['requires_resolution'])

        plan = {
            'parents': [],
            'personnel_checks': checks,
            'requires_year_confirmation': False,
            'requires_snapshot_update_option': False,
        }
        _, errors = merge_user_decisions(plan, {})
        self.assertTrue(any('99999999' in e for e in errors))

        dkey = decision_key_for('99999999', 'D-100.0001')
        plan2, errors2 = merge_user_decisions(
            plan,
            {f'personnel_action__{dkey}': 'ignore'},
        )
        self.assertEqual(errors2, [])
        self.assertEqual(plan2['personnel_decisions'][dkey], 'ignore')

        notes = apply_personnel_decisions(
            checks,
            {dkey: 'ignore'},
            as_of=date(2026, 7, 1),
        )
        self.assertTrue(any('ignored' in n for n in notes))

    def test_create_employee_pending(self):
        checks = build_personnel_checks(
            [self._entry('99999999', '1300.00', booking='2026-06-15')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        dkey = checks[0]['decision_key']
        notes = apply_personnel_decisions(
            checks, {dkey: 'create_employee'}, as_of=date(2026, 7, 1),
        )
        emp = Employee.objects.get(employee_number='99999999')
        self.assertTrue(emp.is_pending)
        self.assertTrue(emp.check_needed)
        self.assertIsNone(emp.user_id)
        self.assertEqual(emp.last_name, 'Hallmann')  # from buchungstext fallback in entry
        contract = emp.contracts.first()
        self.assertIsNotNone(contract)
        self.assertTrue(contract.check_needed)
        # base = excel / multi = 1300 / 1.3 = 1000 (not inflated by FA 1%)
        self.assertEqual(contract.monthly_salary, Decimal('1000.00'))
        fa = emp.allocations.first()
        self.assertIsNotNone(fa)
        self.assertEqual(fa.workhours_percentage, Decimal('1.00'))
        self.assertTrue(any('pending employee' in n for n in notes))

    def test_create_employee_salary_not_inflated_by_placeholder_fa(self):
        """Regression: Excel 7209.33 must not become ~554k via / (multi × 1%)."""
        checks = build_personnel_checks(
            [self._entry('50011020', '7209.33', booking='2026-06-30')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        dkey = checks[0]['decision_key']
        apply_personnel_decisions(
            checks, {dkey: 'create_employee'}, as_of=date(2026, 7, 1),
        )
        emp = Employee.objects.get(employee_number='50011020')
        contract = emp.contracts.get()
        # 7209.33 / 1.3 = 5545.64
        self.assertEqual(contract.monthly_salary, Decimal('5545.64'))
        self.assertLess(contract.monthly_salary, Decimal('10000'))

    def test_no_allocation_create_fa(self):
        other_wbs = WBSElement.objects.create(
            wbs_code='D-100.0099',
            title='Other PSP',
            cost_center=self.cc,
            has_personnel_costs=True,
        )
        emp2 = Employee.objects.create(
            employee_number='50009999',
            first_name='Max',
            last_name='Mustermann',
        )
        c2 = Contract.objects.create(
            employee=emp2,
            valid_from=date(2025, 1, 1),
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('3000.00'),
            is_active=True,
        )
        FundingAllocation.objects.create(
            contract=c2,
            employee=emp2,
            wbs_element=other_wbs,
            workhours_percentage=Decimal('50.00'),
            start_date=date(2025, 1, 1),
            end_date=None,
        )

        checks = build_personnel_checks(
            [self._entry('50009999', '1000.00')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(checks[0]['status'], 'no_allocation')
        self.assertEqual(checks[0]['case'], 'b')
        dkey = checks[0]['decision_key']
        apply_personnel_decisions(
            checks, {dkey: 'create_fa'}, as_of=date(2026, 7, 1),
        )
        emp2.refresh_from_db()
        self.assertTrue(emp2.check_needed)
        fa = FundingAllocation.objects.filter(
            employee=emp2, wbs_element=self.wbs,
        ).first()
        self.assertIsNotNone(fa)
        self.assertEqual(fa.workhours_percentage, Decimal('1.00'))

    def test_contract_split_when_100_percent(self):
        # Fill contract to 100% with active FA
        self.alloc.workhours_percentage = Decimal('100.00')
        self.alloc.save()
        # Entry for different PSP → no_allocation on D-100.0002
        wbs2 = WBSElement.objects.create(
            wbs_code='D-100.0002',
            title='Second',
            cost_center=self.cc,
            has_personnel_costs=True,
        )
        entry = self._entry('50001094', '100.00')
        entry['parent_psp_code'] = 'D-100.0002'
        entry['psp_code'] = 'D-100.0002.2'
        checks = build_personnel_checks([entry], 'D-100.0002', as_of=date(2026, 7, 1))
        self.assertEqual(checks[0]['status'], 'no_allocation')
        self.assertTrue(checks[0]['will_split_contract'])
        dkey = checks[0]['decision_key']
        apply_personnel_decisions(
            checks, {dkey: 'create_fa'}, as_of=date(2026, 7, 1),
        )
        self.contract.refresh_from_db()
        self.assertFalse(self.contract.is_active)
        new_contracts = Contract.objects.filter(
            employee=self.employee, check_needed=True,
        ).exclude(pk=self.contract.pk)
        self.assertEqual(new_contracts.count(), 1)
        new_c = new_contracts.first()
        fa = FundingAllocation.objects.filter(
            employee=self.employee, wbs_element=wbs2, contract=new_c,
        ).first()
        self.assertIsNotNone(fa)

    def test_january_tolerance_is_4_percent(self):
        self.assertEqual(
            tolerance_for_booking_date(date(2026, 1, 15)),
            Decimal('0.04'),
        )
        self.assertEqual(
            tolerance_for_booking_date(date(2026, 6, 15)),
            Decimal('0.025'),
        )
        # 2.6% off expected 2600 = 2667.6 — fails at 2.5%, passes at 4%
        checks = build_personnel_checks(
            [self._entry('50001094', '2667.60', booking='2026-01-31')],
            'D-100.0001',
            as_of=date(2026, 2, 1),
        )
        self.assertEqual(checks[0]['status'], 'match')

    def test_part_time_and_supplements_in_expected_amount(self):
        self.contract.weekly_hours = Decimal('19.50')
        self.contract.save()
        SalarySupplement.objects.create(
            contract=self.contract,
            employee=self.employee,
            percentage=Decimal('5.00'),
        )
        SalarySupplement.objects.create(
            contract=self.contract,
            employee=self.employee,
            fixed_amount=Decimal('250.00'),
        )
        checks = build_personnel_checks(
            [self._entry('50001094', '1446.25')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(checks[0]['status'], 'match')
        self.assertEqual(checks[0]['expected_amount'], '1446.25')

    def test_suggest_salary_accounts_for_hours(self):
        self.contract.weekly_hours = Decimal('19.50')
        self.contract.save()
        checks = build_personnel_checks(
            [self._entry('50001094', '1625.00')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(checks[0]['status'], 'mismatch')
        self.assertEqual(checks[0]['suggested_monthly_salary'], '5000.00')

    def test_fa_outside_booking_month_is_no_allocation(self):
        self.alloc.end_date = date(2025, 12, 31)
        self.alloc.save()
        checks = build_personnel_checks(
            [self._entry('50001094', '2600.00', booking='2026-06-01')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(checks[0]['status'], 'no_allocation')
        self.assertEqual(checks[0]['case'], 'b')
