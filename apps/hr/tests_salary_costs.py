"""Tests for contract salary (100%) and true-cost calculations."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.core.models import GlobalSetting
from apps.hr.models import Contract, Employee, SalarySupplement


class ContractSalaryCostsTests(TestCase):
    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'default_weekly_hours': Decimal('39.00'),
                'true_cost_multiplicator': Decimal('1.300'),
            },
        )
        self.employee = Employee.objects.create(
            employee_number='E-SAL-1',
            first_name='Test',
            last_name='Person',
        )

    def _contract(self, salary='4000.00', hours='39.00', **kwargs):
        return Contract.objects.create(
            employee=self.employee,
            valid_from=date(2026, 1, 1),
            weekly_hours=Decimal(hours),
            monthly_salary=Decimal(salary),
            is_active=True,
            **kwargs,
        )

    def test_full_time_base_true_costs(self):
        contract = self._contract()
        self.assertEqual(contract.get_monthly_salary(), Decimal('4000.00'))
        self.assertEqual(contract.get_salary_supplements_total(), Decimal('0.00'))
        self.assertEqual(contract.get_monthly_salary_with_supplements(), Decimal('4000.00'))
        self.assertEqual(contract.get_workload_fraction(), Decimal('1.0000'))
        # 4000 × 1 × 1.3
        self.assertEqual(contract.get_monthly_costs(), Decimal('5200.00'))

    def test_part_time_scales_true_costs(self):
        contract = self._contract(hours='19.50')
        self.assertEqual(contract.get_workload_fraction(), Decimal('0.5000'))
        # 4000 × 0.5 × 1.3 = 2600
        self.assertEqual(contract.get_monthly_costs(), Decimal('2600.00'))
        # Base salary field stays full-time reference
        self.assertEqual(contract.get_monthly_salary(), Decimal('4000.00'))

    def test_percentage_supplement_added_at_100_percent(self):
        contract = self._contract()
        SalarySupplement.objects.create(
            contract=contract,
            employee=self.employee,
            percentage=Decimal('5.00'),
        )
        # 4000 + 5% = 4200; true costs 4200 × 1.3 = 5460
        self.assertEqual(contract.get_salary_supplements_total(), Decimal('200.00'))
        self.assertEqual(contract.get_monthly_salary_with_supplements(), Decimal('4200.00'))
        self.assertEqual(contract.get_monthly_costs(), Decimal('5460.00'))

    def test_fixed_supplement_added_and_scaled_with_hours(self):
        contract = self._contract(hours='19.50')
        SalarySupplement.objects.create(
            contract=contract,
            employee=self.employee,
            fixed_amount=Decimal('250.00'),
        )
        # gehalt_100% = 4250; × 0.5 × 1.3 = 2762.50
        self.assertEqual(contract.get_monthly_salary_with_supplements(), Decimal('4250.00'))
        self.assertEqual(contract.get_monthly_costs(), Decimal('2762.50'))

    def test_combined_supplements_and_part_time(self):
        contract = self._contract(salary='4000.00', hours='19.50')
        SalarySupplement.objects.create(
            contract=contract,
            employee=self.employee,
            percentage=Decimal('5.00'),
        )
        SalarySupplement.objects.create(
            contract=contract,
            employee=self.employee,
            fixed_amount=Decimal('250.00'),
        )
        # 4000 + 200 + 250 = 4450; × 0.5 × 1.3 = 2892.50
        self.assertEqual(contract.get_monthly_salary_with_supplements(), Decimal('4450.00'))
        self.assertEqual(contract.get_monthly_costs(), Decimal('2892.50'))

    def test_suggest_base_salary_reverses_supplements_and_hours(self):
        contract = self._contract(salary='4000.00', hours='19.50')
        SalarySupplement.objects.create(
            contract=contract,
            employee=self.employee,
            percentage=Decimal('5.00'),
        )
        SalarySupplement.objects.create(
            contract=contract,
            employee=self.employee,
            fixed_amount=Decimal('250.00'),
        )
        # FA 60% of weekly hours: expected true on PSP =
        # 4450 × 0.5 × 1.3 × 0.6 = 1735.50
        excel = Decimal('1735.50')
        suggested = contract.suggest_base_monthly_salary_for_allocation_amount(
            excel, Decimal('60.00')
        )
        self.assertEqual(suggested, Decimal('4000.00'))

    def test_employee_get_monthly_costs_delegates(self):
        contract = self._contract(hours='19.50')
        self.assertEqual(self.employee.get_monthly_costs(), contract.get_monthly_costs())
