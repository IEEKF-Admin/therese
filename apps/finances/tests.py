from datetime import date
from io import BytesIO

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from apps.accounts.models import CustomUser
from apps.finances.forms import (
    CostCenterForm,
    CostCenterYearEstimateFormSet,
    WBSElementForm,
    WBSElementYearEstimateFormSet,
)
from apps.finances.models import CostCenter, WBSElement, WBSElementYearEstimate
from apps.finances.views.psp_crud import PSPUpdateView
from apps.hr.models import Employee, Workgroup


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
        estimate_2026 = WBSElementYearEstimate.objects.get(wbs_element=self.psp, year=2026)
        self.assertEqual(estimate_2026.funding, 1000.00)


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


class PSPUpdateViewTests(TestCase):
    def setUp(self):
        self.cost_center = CostCenter.objects.create(cost_center='4711/2031')
        self.pi = Employee.objects.create(
            employee_number='E-PSP-PI',
            first_name='Pat',
            last_name='Principal',
        )
        self.workgroup_a = Workgroup.objects.create(
            short_name='Lab-A',
            long_name='Lab A',
            pi=self.pi,
        )
        self.workgroup_b = Workgroup.objects.create(
            short_name='Lab-B',
            long_name='Lab B',
            pi=self.pi,
        )
        self.user = CustomUser.objects.create_user('psp-manager', password='test')
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        self.employee = Employee.objects.create(
            employee_number='E-PSP-MGR',
            first_name='Manager',
            last_name='User',
            user=self.user,
        )
        self.workgroup_a.members.add(self.employee)
        manage_perm = Permission.objects.get(
            codename='manage_psp_element',
            content_type=ContentType.objects.get(app_label='finances', model='wbselement'),
        )
        self.user.user_permissions.add(manage_perm)
        self.psp_other_group = WBSElement.objects.create(
            wbs_code='WBS-OTHER-1',
            title='Other group PSP',
            cost_center=self.cost_center,
            work_group=self.workgroup_b,
        )

    def test_get_form_is_not_bound_and_loads_instance_values(self):
        factory = RequestFactory()
        request = factory.get(f'/finances/psp/manage/{self.psp_other_group.pk}/edit/')
        request.user = self.user

        view = PSPUpdateView()
        view.setup(request, pk=self.psp_other_group.pk)
        view.object = view.get_object()
        form = view.get_form()

        self.assertFalse(form.is_bound)
        self.assertEqual(form['wbs_code'].value(), 'WBS-OTHER-1')
        self.assertEqual(form['title'].value(), 'Other group PSP')
        self.assertEqual(form['work_group'].value(), self.workgroup_b.pk)

    def test_manager_can_open_psp_from_other_workgroup(self):
        factory = RequestFactory()
        request = factory.get(f'/finances/psp/manage/{self.psp_other_group.pk}/edit/')
        request.user = self.user

        response = PSPUpdateView.as_view()(request, pk=self.psp_other_group.pk)
        response.render()
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('WBS-OTHER-1', content)
        self.assertIn('Other group PSP', content)
        self.assertNotIn('Dieses Feld ist zwingend erforderlich.', content)


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
            data[f'{prefix}-consumables_estimate'] = row.get('consumables_estimate', '')
            data[f'{prefix}-travel_estimate'] = row.get('travel_estimate', '')
            data[f'{prefix}-animal_costs_estimate'] = row.get('animal_costs_estimate', '')
            data[f'{prefix}-id'] = row.get('id', '')
            data[f'{prefix}-DELETE'] = row.get('DELETE', '')
        return data

    def test_unique_years_save_with_lomv(self):
        formset = CostCenterYearEstimateFormSet(
            self._formset_data([
                {'year': '2026', 'lomv': '3000.00'},
                {'year': '2027', 'lomv': '3500.00'},
            ]),
            instance=self.cost_center,
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.cost_center.year_estimates.count(), 2)
        estimate = self.cost_center.year_estimates.get(year=2026)
        self.assertEqual(estimate.lomv, 3000.00)