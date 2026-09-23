"""Tests for PSP Plan / True / Obligo overview."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

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
    funding_cost_breakdown,
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
        calc = funding_cost_breakdown(
            self.alloc, date(2026, 1, 1), date(2026, 12, 31)
        )
        self.assertEqual(calc['base_salary'], Decimal('1000.00'))
        self.assertEqual(calc['monthly_true_cost'], Decimal('1300.00'))
        self.assertEqual(calc['monthly_allocated'], Decimal('650.00'))
        self.assertEqual(calc['months'], 12)
        self.assertEqual(calc['period_cost'], Decimal('7800.00'))
        self.assertEqual(calc['overlap_start'], date(2026, 1, 1))
        self.assertEqual(calc['overlap_end'], date(2026, 12, 31))

    def test_uses_payscale_instance_for_each_month(self):
        from apps.finances.models import PayScale

        PayScale.objects.create(
            pay_scale_group='E13', experience_level=1,
            monthly_salary=Decimal('1000.00'), effective_as_of=date(2026, 1, 1),
        )
        PayScale.objects.create(
            pay_scale_group='E13', experience_level=1,
            monthly_salary=Decimal('2000.00'), effective_as_of=date(2026, 7, 1),
        )
        self.contract.pay_scale_group = 'E13'
        self.contract.experience_level = 1
        self.contract.save()
        cost = calculate_funding_cost(
            self.alloc, date(2026, 1, 1), date(2026, 12, 31),
        )
        # Jan–Jun: 1000 × 1.3 × 50% × 6 = 3900
        # Jul–Dec: 2000 × 1.3 × 50% × 6 = 7800
        self.assertEqual(cost, Decimal('11700.00'))
        calc = funding_cost_breakdown(
            self.alloc, date(2026, 1, 1), date(2026, 12, 31),
        )
        self.assertTrue(calc['has_varying_monthly_cost'])
        self.assertEqual(len(calc['monthly_cost_runs']), 2)
        self.assertEqual(calc['monthly_cost_runs'][0]['months'], 6)
        self.assertEqual(calc['monthly_cost_runs'][0]['allocated'], Decimal('650.00'))
        self.assertEqual(calc['monthly_cost_runs'][1]['allocated'], Decimal('1300.00'))

    def test_uses_occupation_instance_for_each_month(self):
        from apps.core.models import OccupationSalaryTable
        from apps.core.occupation_salary import add_occupation_row

        table = OccupationSalaryTable.objects.create(name='BG-PSP')
        add_occupation_row(table, Decimal('39.000'), Decimal('1000.00'), as_of=date(2026, 1, 1))
        add_occupation_row(table, Decimal('39.000'), Decimal('2000.00'), as_of=date(2026, 7, 1))
        self.employee.salary_table = table
        self.employee.save(update_fields=['salary_table'])
        self.contract.weekly_hours = Decimal('39.000')
        self.contract.save()
        cost = calculate_funding_cost(
            self.alloc, date(2026, 1, 1), date(2026, 12, 31),
        )
        self.assertEqual(cost, Decimal('11700.00'))


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
            personnel_costs=Decimal('8000.00'),  # Ist for personnel Actual
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

    def test_personnel_actual_is_ist_plus_obligo_plus_not_booked(self):
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2026, 1, 1)
        self.wbs.period_end = date(2026, 12, 31)
        self.wbs.save()

        overview = build_psp_financial_overview(
            self.wbs, 2026, Decimal('1.300'), as_of=date(2026, 1, 1),
        )
        self.assertEqual(overview['plan_scope'], 'lifetime')
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['material_costs']['plan'], Decimal('10000.00'))
        self.assertEqual(by_field['material_costs']['true'], Decimal('2000.00'))
        self.assertEqual(by_field['material_costs']['obligo'], Decimal('500.00'))

        # Not booked: 2000 * 1.3 * 100% * 12 = 31200 (import_completed=False, from 1.1.)
        self.assertEqual(by_field['personnel_costs']['not_booked'], Decimal('31200.00'))
        self.assertEqual(by_field['personnel_costs']['imported_true'], Decimal('8000.00'))
        self.assertEqual(by_field['personnel_costs']['obligo'], Decimal('3000.00'))
        # Actual = Ist 8000 + Obligo 3000 + Not booked 31200 = 42200
        self.assertEqual(by_field['personnel_costs']['true'], Decimal('42200.00'))
        self.assertEqual(by_field['personnel_costs']['true_source'], 'ist_obligo_not_booked')
        self.assertEqual(overview['personal_obligo'], Decimal('3000.00'))
        self.assertEqual(len(overview['personnel_rows']), 1)
        self.assertEqual(by_field['material_costs']['label_de'], 'Sachkosten')
        self.assertNotIn('.', by_field['personnel_costs']['label_de'])
        # Material: 10000 - 2000 - 500 - 0 = 7500
        self.assertEqual(by_field['material_costs']['free_budget'], Decimal('7500.00'))
        # Personnel Free = Budget − Actual = 50000 - 42200 = 7800
        self.assertEqual(by_field['personnel_costs']['free_budget'], Decimal('7800.00'))
        self.assertIsNone(by_field['material_costs']['not_booked'])
        # Booked = Ist + Obligo (without Not booked)
        self.assertEqual(by_field['material_costs']['booked'], Decimal('2500.00'))
        self.assertEqual(by_field['personnel_costs']['booked'], Decimal('11000.00'))

    def test_cost_type_comment_is_passed_to_row(self):
        self.wbs.comment_personnel_costs = 'Watch overtime'
        self.wbs.save(update_fields=['comment_personnel_costs'])
        overview = build_psp_financial_overview(
            self.wbs, 2026, Decimal('1.300'), as_of=date(2026, 1, 1),
        )
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['personnel_costs']['comment'], 'Watch overtime')
        self.assertEqual(by_field['material_costs']['comment'], '')

    def test_not_booked_excludes_import_completed_allocations(self):
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2026, 1, 1)
        self.wbs.period_end = date(2026, 12, 31)
        self.wbs.save()
        FundingAllocation.objects.filter(employee=self.employee, wbs_element=self.wbs).update(
            import_completed=True,
        )
        overview = build_psp_financial_overview(
            self.wbs, 2026, Decimal('1.300'), as_of=date(2026, 1, 1),
        )
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['personnel_costs']['not_booked'], Decimal('0.00'))
        # Actual = Ist 8000 + Obligo 3000 + Not booked 0 = 11000
        self.assertEqual(by_field['personnel_costs']['true'], Decimal('11000.00'))
        # Free = Budget − Actual = 50000 - 11000 = 39000
        self.assertEqual(by_field['personnel_costs']['free_budget'], Decimal('39000.00'))

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
            self.wbs, 2026, Decimal('1.300'), as_of=date(2026, 7, 1),
        )
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['personnel_costs']['not_booked'], Decimal('7800.00'))
        # Year 2027 has no overlapping allocation months → not booked 0
        overview_2027 = build_psp_financial_overview(
            self.wbs, 2027, Decimal('1.300'), as_of=date(2026, 7, 1),
        )
        by_field_2027 = {r['amount_field']: r for r in overview_2027['cost_rows']}
        self.assertEqual(by_field_2027['personnel_costs']['not_booked'], Decimal('0.00'))

    def test_not_booked_only_future_months(self):
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2026, 1, 1)
        self.wbs.period_end = date(2026, 12, 31)
        self.wbs.save()
        overview = build_psp_financial_overview(
            self.wbs, 2026, Decimal('1.300'), as_of=date(2026, 9, 15),
        )
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        # Remaining Sep–Dec = 4 months: 2000 * 1.3 * 100% * 4 = 10400
        self.assertEqual(by_field['personnel_costs']['not_booked'], Decimal('10400.00'))
        self.assertEqual(overview['personnel_rows'][0]['not_booked_calc']['months'], 4)
        self.assertEqual(
            overview['personnel_rows'][0]['not_booked_calc']['overlap_start'],
            date(2026, 9, 15),
        )
        # Actual = Ist 8000 + Obligo 3000 + Not booked 10400 = 21400
        self.assertEqual(by_field['personnel_costs']['true'], Decimal('21400.00'))
        self.assertEqual(by_field['personnel_costs']['free_budget'], Decimal('28600.00'))

    def test_not_booked_zero_when_year_already_past(self):
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2026, 1, 1)
        self.wbs.period_end = date(2026, 12, 31)
        self.wbs.save()
        overview = build_psp_financial_overview(
            self.wbs, 2026, Decimal('1.300'), as_of=date(2027, 1, 1),
        )
        by_field = {r['amount_field']: r for r in overview['cost_rows']}
        self.assertEqual(by_field['personnel_costs']['not_booked'], Decimal('0.00'))
        # Actual = Ist 8000 + Obligo 3000 + 0 = 11000
        self.assertEqual(by_field['personnel_costs']['true'], Decimal('11000.00'))

    def test_non_annual_plan_not_tied_to_filter_year(self):
        """Lifetime plan is shown even when the filter year differs from estimate.year."""
        self.wbs.subject_to_annual_recurrence = False
        self.wbs.period_start = date(2025, 1, 1)
        self.wbs.period_end = date(2028, 12, 31)
        self.wbs.save()
        # Estimate stored under 2025 (technical key), filter year 2027
        WBSElementYearEstimate.objects.filter(wbs_element=self.wbs).update(year=2025)
        overview = build_psp_financial_overview(
            self.wbs, 2027, Decimal('1.300'), as_of=date(2026, 1, 1),
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
        self.assertContains(response, 'Booked Costs')
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
        self.assertContains(response, 'Personalkosten in the overview')
        self.assertContains(response, 'Back to PSP overview')

    @patch(
        'apps.finances.views.psp_overview.resolve_as_of',
        return_value=date(2026, 1, 1),
    )
    def test_personnel_detail_shows_calculation_inputs(self, _as_of):
        wbs = WBSElement.objects.get(wbs_code='P-VIEW.1')
        wbs.has_personnel_costs = True
        wbs.subject_to_annual_recurrence = True
        wbs.save()
        employee = Employee.objects.create(
            employee_number='E-PSP-DET',
            first_name='Niels',
            last_name='Bohr',
        )
        contract = Contract.objects.create(
            employee=employee,
            valid_from=date(2026, 1, 1),
            weekly_hours=Decimal('39.00'),
            monthly_salary=Decimal('1000.00'),
            is_active=True,
        )
        FundingAllocation.objects.create(
            contract=contract,
            employee=employee,
            wbs_element=wbs,
            workhours_percentage=Decimal('50.00'),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            import_completed=False,
        )
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={'true_cost_multiplicator': Decimal('1.300')},
        )
        response = self.client.get(f'/finances/psp-elements/{wbs.pk}/personnel/?year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Niels Bohr')
        self.assertContains(response, 'Base salary (100% workload)')
        self.assertContains(response, '1.000,00')
        self.assertContains(response, 'Monthly allocated')
        self.assertContains(response, '650,00')
        self.assertContains(response, 'Inclusive calendar months')
        self.assertContains(response, '7.800,00')
        self.assertContains(response, 'Ist + Personalobligo + Not booked')
        self.assertContains(response, 'Total Actual')
