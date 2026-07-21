"""Tests for PSP Plan / True / Obligo overview."""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase

from apps.accounts.models import CustomUser
from apps.accounts.permissions import assign_permissions_to_groups
from apps.core.models import GlobalSetting
from apps.finances.models import (
    CostCenter,
    WBSElement,
    WBSElementObligo,
    WBSElementTrueYearlySpending,
    WBSElementYearEstimate,
)
from apps.finances.views.psp_overview import (
    build_psp_financial_overview,
    calculate_funding_cost,
)
from apps.hr.models import Contract, Employee, FundingAllocation


class CalculateFundingCostTests(TestCase):
    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={'true_cost_multiplicator': Decimal('1.300')},
        )
        self.employee = Employee.objects.create(
            employee_number='E-PSP-1',
            first_name='Ada',
            last_name='Lovelace',
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            valid_from=date(2026, 1, 1),
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('1000.00'),
            is_active=True,
        )
        self.cc = CostCenter.objects.create(cost_center='CC-PSP')
        self.wbs = WBSElement.objects.create(
            wbs_code='P-1.0001',
            title='Overview test',
            cost_center=self.cc,
            has_personnel_costs=True,
            has_material_costs=True,
        )
        self.alloc = FundingAllocation.objects.create(
            contract=self.contract,
            employee=self.employee,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('50.00'),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )

    def test_true_cost_uses_multiplicator_and_percentage(self):
        # 1000 * 1.3 * 50% * 12 months = 7800
        cost = calculate_funding_cost(
            self.alloc, date(2026, 1, 1), date(2026, 12, 31)
        )
        self.assertEqual(cost, Decimal('7800.00'))


class BuildPspOverviewTests(TestCase):
    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={'true_cost_multiplicator': Decimal('1.300')},
        )
        self.cc = CostCenter.objects.create(cost_center='CC-OV')
        self.wbs = WBSElement.objects.create(
            wbs_code='P-2.0001',
            title='Financial table',
            cost_center=self.cc,
            has_material_costs=True,
            has_personnel_costs=True,
        )
        WBSElementYearEstimate.objects.create(
            wbs_element=self.wbs,
            year=2026,
            material_costs=Decimal('10000.00'),
            personnel_costs=Decimal('50000.00'),
        )
        WBSElementTrueYearlySpending.objects.create(
            wbs_element=self.wbs,
            date_of_update=date(2026, 6, 1),
            material_costs=Decimal('2000.00'),
            personnel_costs=Decimal('99999.00'),  # imported; overview must NOT use this
        )
        WBSElementObligo.objects.create(
            wbs_element=self.wbs,
            date_of_update=date(2026, 6, 1),
            material_costs=Decimal('500.00'),
            personal=Decimal('3000.00'),
        )
        self.employee = Employee.objects.create(
            employee_number='E-PSP-2',
            first_name='Grace',
            last_name='Hopper',
        )
        contract = Contract.objects.create(
            employee=self.employee,
            valid_from=date(2026, 1, 1),
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('2000.00'),
            is_active=True,
        )
        FundingAllocation.objects.create(
            contract=contract,
            employee=self.employee,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('100.00'),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )

    def test_overview_uses_real_personnel_not_imported_true(self):
        # Default WBS is non-annual → lifetime plan + full-runtime personnel
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2026, 1, 1)
        self.wbs.period_end = date(2026, 12, 31)
        self.wbs.save()

        overview = build_psp_financial_overview(
            self.wbs, 2026, Decimal('1.300')
        )
        self.assertEqual(overview['plan_scope'], 'lifetime')
        self.assertEqual(overview['personnel_scope'], 'lifetime')
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['material_costs']['plan'], Decimal('10000.00'))
        self.assertEqual(by_field['material_costs']['true'], Decimal('2000.00'))
        self.assertEqual(by_field['material_costs']['obligo'], Decimal('500.00'))

        # Real personnel: 2000 * 1.3 * 100% * 12 = 31200
        self.assertEqual(by_field['personnel_costs']['true'], Decimal('31200.00'))
        self.assertEqual(by_field['personnel_costs']['true_source'], 'real_personnel')
        self.assertEqual(
            by_field['personnel_costs']['imported_true'], Decimal('99999.00')
        )
        # Personalobligo is shown in Obligo of Personalkosten, not as own row
        self.assertEqual(by_field['personnel_costs']['obligo'], Decimal('3000.00'))
        self.assertEqual(overview['personal_obligo'], Decimal('3000.00'))
        self.assertEqual(len(overview['personnel_rows']), 1)
        self.assertEqual(by_field['material_costs']['label_de'], 'Sachkosten')
        self.assertNotIn('.', by_field['personnel_costs']['label_de'])
        # Free budget = Budget − Actual − Commitment − Not booked
        # Material: 10000 - 2000 - 500 - 0 = 7500
        self.assertEqual(by_field['material_costs']['free_budget'], Decimal('7500.00'))
        # Personnel: 50000 - 31200 - 3000 - 31200 = -15400
        self.assertEqual(by_field['personnel_costs']['free_budget'], Decimal('-15400.00'))
        # FundingAllocation.import_completed defaults False → not booked
        self.assertEqual(by_field['personnel_costs']['not_booked'], Decimal('31200.00'))
        self.assertIsNone(by_field['material_costs']['not_booked'])

    def test_not_booked_excludes_import_completed_allocations(self):
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2026, 1, 1)
        self.wbs.period_end = date(2026, 12, 31)
        self.wbs.save()
        FundingAllocation.objects.filter(employee=self.employee, wbs_element=self.wbs).update(
            import_completed=True,
        )
        overview = build_psp_financial_overview(
            self.wbs, 2026, Decimal('1.300')
        )
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['personnel_costs']['true'], Decimal('31200.00'))
        self.assertEqual(by_field['personnel_costs']['not_booked'], Decimal('0.00'))
        # Free budget no longer subtracts not booked when none: 50000-31200-3000=15800
        self.assertEqual(by_field['personnel_costs']['free_budget'], Decimal('15800.00'))

    def test_not_booked_uses_selected_year_and_allocation_overlap(self):
        """Not booked uses Year filter + allocation dates + % + multiplicator."""
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2025, 1, 1)
        self.wbs.period_end = date(2028, 12, 31)
        self.wbs.save()
        # Allocation only covers Jul–Dec 2026 at 50%
        FundingAllocation.objects.filter(employee=self.employee).update(
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            workhours_percentage=Decimal('50.00'),
        )
        # salary 2000 * 1.3 * 50% * 6 months = 7800
        overview = build_psp_financial_overview(
            self.wbs, 2026, Decimal('1.300')
        )
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['personnel_costs']['not_booked'], Decimal('7800.00'))
        # Year 2027 has no overlapping allocation months → not booked 0
        overview_2027 = build_psp_financial_overview(
            self.wbs, 2027, Decimal('1.300')
        )
        by_field_2027 = {r['amount_field']: r for r in overview_2027['cost_rows']}
        self.assertEqual(by_field_2027['personnel_costs']['not_booked'], Decimal('0.00'))

    def test_non_annual_plan_not_tied_to_filter_year(self):
        """Lifetime plan is shown even when the filter year differs from estimate.year."""
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2025, 1, 1)
        self.wbs.period_end = date(2028, 12, 31)
        self.wbs.save()
        # Estimate stored under 2025 (technical key), filter year 2027
        WBSElementYearEstimate.objects.filter(wbs_element=self.wbs).update(year=2025)
        overview = build_psp_financial_overview(
            self.wbs, 2027, Decimal('1.300')
        )
        self.assertEqual(overview['plan_scope'], 'lifetime')
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['material_costs']['plan'], Decimal('10000.00'))


class PspOverviewViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        assign_permissions_to_groups()

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            'pspview', password='test', is_superuser=True
        )
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        self.client = Client()
        self.client.login(username='pspview', password='test')
        CostCenter.objects.create(cost_center='CC-V')
        WBSElement.objects.create(
            wbs_code='P-VIEW.1',
            title='Visible',
            cost_center=CostCenter.objects.get(cost_center='CC-V'),
            has_material_costs=True,
        )

    def test_page_loads(self):
        response = self.client.get('/finances/psp-elements/?year=2026&show_empty=1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Budget')
        self.assertContains(response, 'Actual')
        self.assertContains(response, 'Commitment')
        self.assertContains(response, 'Free budget')
        self.assertContains(response, 'P-VIEW.1')
        self.assertNotContains(
            response,
            'No funding allocations on this PSP',
        )

    def test_personnel_detail_page(self):
        wbs = WBSElement.objects.get(wbs_code='P-VIEW.1')
        response = self.client.get(f'/finances/psp-elements/{wbs.pk}/personnel/?year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned personnel')
        self.assertContains(response, 'Back to PSP overview')
