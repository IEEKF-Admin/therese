from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.finances.forms import (
    CostCenterForm,
    CostCenterYearEstimateFormSet,
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
            'third_party_funder_identifier': '',
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
            'third_party_funder_identifier': 'DFG-123',
        })
        self.assertTrue(form.is_valid(), form.errors)
        psp = form.save()
        self.assertEqual(psp.cost_center, self.cost_center)
        self.assertEqual(psp.third_party_funder_identifier, 'DFG-123')

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
            'third_party_funder_identifier': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        psp = form.save()
        self.assertEqual(psp.period_start, date(2026, 3, 1))
        self.assertEqual(psp.period_end, date(2028, 11, 1))

    def test_third_party_funding_commitment_accepts_pdf(self):
        pdf = SimpleUploadedFile('zusage.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        form = WBSElementForm(
            data={
                'wbs_code': 'D-999.0002.3',
                'title': 'Funding file test',
                'work_group': '',
                'responsible_person': '',
                'cost_center': self.cost_center.pk,
                'period_start': '',
                'period_end': '',
                'subject_to_annual_recurrence': False,
                'is_inactive': False,
                'comment': '',
                'third_party_funder_identifier': '',
            },
            files={'third_party_funding_commitment': pdf},
        )
        self.assertTrue(form.is_valid(), form.errors)
        psp = form.save()
        self.assertTrue(psp.third_party_funding_commitment.name.endswith('.pdf'))


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
            data[f'{prefix}-personnel_estimate'] = row.get('personnel_estimate', '')
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
                {'year': '2026', 'funding': '1000.00', 'personnel_estimate': '500.00'},
                {'year': '2027', 'funding': '1500.00'},
            ]),
            instance=self.psp,
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.psp.year_estimates.count(), 2)
        estimate_2026 = WBSElementYearEstimate.objects.get(wbs_element=self.psp, year=2026)
        self.assertEqual(estimate_2026.funding, 1000.00)
        self.assertEqual(estimate_2026.personnel_estimate, 500.00)


class CostCenterFormTests(TestCase):
    def test_valid_form_saves(self):
        form = CostCenterForm(data={
            'cost_center': '4711/2028',
            'comments': 'Test comments',
            'third_party_funder_identifier': 'BMBF-99',
        })
        self.assertTrue(form.is_valid(), form.errors)
        cc = form.save()
        self.assertEqual(cc.cost_center, '4711/2028')
        self.assertEqual(cc.third_party_funder_identifier, 'BMBF-99')

    def test_third_party_funding_commitment_accepts_image(self):
        image = SimpleUploadedFile('zusage.png', BytesIO(b'\x89PNG\r\n').read(), content_type='image/png')
        form = CostCenterForm(
            data={
                'cost_center': '4711/2029',
                'comments': '',
                'third_party_funder_identifier': '',
            },
            files={'third_party_funding_commitment': image},
        )
        self.assertTrue(form.is_valid(), form.errors)
        cc = form.save()
        self.assertTrue(cc.third_party_funding_commitment.name.endswith('.png'))


class CostCenterYearEstimateFormSetTests(TestCase):
    def setUp(self):
        self.cost_center = CostCenter.objects.create(cost_center='4711/2030')

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
            data[f'{prefix}-lomv'] = row.get('lomv', '')
            data[f'{prefix}-personnel_estimate'] = row.get('personnel_estimate', '')
            data[f'{prefix}-consumables_estimate'] = row.get('consumables_estimate', '')
            data[f'{prefix}-travel_estimate'] = row.get('travel_estimate', '')
            data[f'{prefix}-animal_costs_estimate'] = row.get('animal_costs_estimate', '')
            data[f'{prefix}-id'] = row.get('id', '')
            data[f'{prefix}-DELETE'] = row.get('DELETE', '')
        return data

    def test_unique_years_save_with_lomv(self):
        formset = CostCenterYearEstimateFormSet(
            self._formset_data([
                {'year': '2026', 'lomv': '3000.00', 'personnel_estimate': '1200.00'},
                {'year': '2027', 'lomv': '3500.00'},
            ]),
            instance=self.cost_center,
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.cost_center.year_estimates.count(), 2)
        estimate = self.cost_center.year_estimates.get(year=2026)
        self.assertEqual(estimate.lomv, 3000.00)
        self.assertEqual(estimate.personnel_estimate, 1200.00)