from datetime import date

from django.test import TestCase

from apps.finances.forms import (
    WBSElementForm,
    WBSElementYearEstimateFormSet,
)
from apps.finances.models import CostCenter, WBSElement, WBSElementYearEstimate


class WBSElementFormTests(TestCase):
    def setUp(self):
        self.cost_center = CostCenter.objects.create(cost_center='4711/2026')

    def test_cost_center_required_in_editor(self):
        form = WBSElementForm(data={
            'wbs_code': 'D-999.0001.1',
            'title': 'Test PSP',
            'work_group': '',
            'responsible_person': '',
            'cost_center': '',
            'period_start': '',
            'period_end': '',
            'subject_to_annual_recurrence': False,
            'is_inactive': False,
            'comment': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('cost_center', form.errors)

    def test_valid_form_saves_with_cost_center(self):
        form = WBSElementForm(data={
            'wbs_code': 'D-999.0002.1',
            'title': 'Test PSP 2',
            'work_group': '',
            'responsible_person': '',
            'cost_center': self.cost_center.pk,
            'period_start': '',
            'period_end': '',
            'subject_to_annual_recurrence': False,
            'is_inactive': False,
            'comment': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        psp = form.save()
        self.assertEqual(psp.cost_center, self.cost_center)

    def test_period_month_picker_parses_and_saves(self):
        form = WBSElementForm(data={
            'wbs_code': 'D-999.0002.2',
            'title': 'Period test',
            'work_group': '',
            'responsible_person': '',
            'cost_center': self.cost_center.pk,
            'period_start': '2026-03',
            'period_end': '2028-11',
            'subject_to_annual_recurrence': False,
            'is_inactive': False,
            'comment': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        psp = form.save()
        self.assertEqual(psp.period_start, date(2026, 3, 1))
        self.assertEqual(psp.period_end, date(2028, 11, 1))


class WBSElementYearEstimateFormSetTests(TestCase):
    def setUp(self):
        self.cost_center = CostCenter.objects.create(cost_center='4711/2027')
        self.psp = WBSElement.objects.create(
            wbs_code='D-999.0003.1',
            title='Estimate test',
            cost_center=self.cost_center,
        )

    def _formset_data(self, rows):
        prefix_base = 'year_estimates'
        data = {
            f'{prefix_base}-TOTAL_FORMS': str(len(rows)),
            f'{prefix_base}-INITIAL_FORMS': '0',
            f'{prefix_base}-MIN_NUM_FORMS': '0',
            f'{prefix_base}-MAX_NUM_FORMS': '1000',
        }
        for index, row in enumerate(rows):
            prefix = f'{prefix_base}-{index}'
            data[f'{prefix}-year'] = row.get('year', '')
            data[f'{prefix}-funding'] = row.get('funding', '')
            data[f'{prefix}-consumables_estimate'] = row.get('consumables_estimate', '')
            data[f'{prefix}-travel_estimate'] = row.get('travel_estimate', '')
            data[f'{prefix}-animal_costs_estimate'] = row.get('animal_costs_estimate', '')
            data[f'{prefix}-id'] = row.get('id', '')
            data[f'{prefix}-DELETE'] = row.get('DELETE', '')
        return data

    def test_duplicate_year_blocks_save(self):
        formset = WBSElementYearEstimateFormSet(
            self._formset_data([
                {'year': '2026', 'funding': '1000.00'},
                {'year': '2026', 'funding': '2000.00'},
            ]),
            instance=self.psp,
        )
        self.assertFalse(formset.is_valid())
        self.assertTrue(formset.non_form_errors)

    def test_unique_years_save_successfully(self):
        formset = WBSElementYearEstimateFormSet(
            self._formset_data([
                {'year': '2026', 'funding': '1000.00'},
                {'year': '2027', 'funding': '1500.00'},
            ]),
            instance=self.psp,
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.psp.year_estimates.count(), 2)
        self.assertEqual(
            WBSElementYearEstimate.objects.get(wbs_element=self.psp, year=2026).funding,
            1000.00,
        )