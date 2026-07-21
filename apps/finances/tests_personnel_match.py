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
)
from apps.finances.report_import.service import merge_user_decisions
from apps.hr.models import Contract, Employee, FundingAllocation


class PersonnelMatchTests(TestCase):
    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={'true_cost_multiplicator': Decimal('1.300')},
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

    def _entry(self, personalnummer='50001094', amount='2600.00'):
        return {
            'personalnummer': personalnummer,
            'kostenart': '60003000',
            'personalkosten': amount,
            'belegdatum': '2026-06-01',
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
        self.assertEqual(checks[0]['expected_amount'], '2600.00')
        notes = apply_personnel_decisions(checks, {}, as_of=date(2026, 7, 1))
        self.alloc.refresh_from_db()
        self.assertTrue(self.alloc.import_completed)
        self.assertTrue(any('import_completed=Yes' in n for n in notes))

    def test_mismatch_adjust_salary(self):
        # Excel 3250 vs expected 2600 → mismatch;
        # suggested monthly = 3250 / (1.3 × 0.5) = 5000; also sets import_completed
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
        self.assertTrue(any('monthly salary set' in n for n in notes))

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

    def test_no_employee_blocks_without_ignore(self):
        checks = build_personnel_checks(
            [self._entry('99999999', '1000.00')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(checks[0]['status'], 'no_employee')
        self.assertTrue(checks[0]['requires_resolution'])
        self.assertIn('existiert noch nicht', checks[0]['message'])

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

    def test_no_allocation_blocks_without_ignore(self):
        other_wbs = WBSElement.objects.create(
            wbs_code='D-100.0099',
            title='Other PSP',
            cost_center=self.cc,
            has_personnel_costs=True,
        )
        # Employee exists but FA is only on other PSP / none on D-100.0001 — wait,
        # setUp already put FA on D-100.0001. Use a different employee without FA.
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
        # FA only on other WBS — not the imported parent
        FundingAllocation.objects.create(
            contract=c2,
            employee=emp2,
            wbs_element=other_wbs,
            workhours_percentage=Decimal('100.00'),
            start_date=date(2025, 1, 1),
            end_date=None,
        )

        checks = build_personnel_checks(
            [self._entry('50009999', '1000.00')],
            'D-100.0001',
            as_of=date(2026, 7, 1),
        )
        self.assertEqual(checks[0]['status'], 'no_allocation')
        self.assertTrue(checks[0]['requires_resolution'])
        self.assertIn('Funding Allocation', checks[0]['message'])

        plan = {
            'parents': [],
            'personnel_checks': checks,
            'requires_year_confirmation': False,
            'requires_snapshot_update_option': False,
        }
        _, errors = merge_user_decisions(plan, {})
        self.assertTrue(any('50009999' in e for e in errors))

        dkey = checks[0]['decision_key']
        _, errors2 = merge_user_decisions(
            plan,
            {f'personnel_action__{dkey}': 'ignore'},
        )
        self.assertEqual(errors2, [])
