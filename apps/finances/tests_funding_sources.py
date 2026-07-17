from datetime import date

from django.test import TestCase

from apps.finances.funding_sources import (
    apply_funding_source,
    build_funding_source_choices,
    funding_source_value_for_instance,
)
from apps.finances.models import CostCenter, WBSElement
from apps.hr.forms import FundingAllocationForm
from apps.hr.models import Employee, FundingAllocation


class FundingSourceChoicesTests(TestCase):
    def setUp(self):
        self.cost_center = CostCenter.objects.create(cost_center='4711/2099')
        self.psp = WBSElement.objects.create(
            wbs_code='FUND-CC-1',
            title='Funding PSP',
            cost_center=self.cost_center,
        )
        self.employee = Employee.objects.create(
            employee_number='E-FUND-1',
            first_name='Fund',
            last_name='User',
        )

    def test_choices_include_psp_and_cost_center(self):
        flat_values = []
        for entry in build_funding_source_choices():
            if isinstance(entry[1], list):
                flat_values.extend(value for value, _label in entry[1])
            else:
                flat_values.append(entry[0])

        self.assertIn(f'wbs:{self.psp.pk}', flat_values)
        self.assertIn(f'cc:{self.cost_center.pk}', flat_values)

    def test_employee_funding_form_saves_cost_center_allocation(self):
        form = FundingAllocationForm(data={
            'funding_source': f'cc:{self.cost_center.pk}',
            'workhours_percentage': '50.00',
            'plan_position_number': '',
            'start_date': date(2026, 1, 1),
            'end_date': '',
            'comments': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        allocation = form.save(commit=False)
        allocation.employee = self.employee
        allocation.save()

        saved = FundingAllocation.objects.get(pk=allocation.pk)
        self.assertIsNone(saved.wbs_element_id)
        self.assertEqual(saved.cost_center_id, self.cost_center.pk)
        self.assertEqual(
            funding_source_value_for_instance(saved),
            f'cc:{self.cost_center.pk}',
        )