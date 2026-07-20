from datetime import date
from io import BytesIO

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import Client, RequestFactory, TestCase

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups
from apps.finances.forms import (
    CostCenterForm,
    CostCenterYearEstimateFormSet,
    WBSElementForm,
    WBSElementYearEstimateFormSet,
)
from apps.finances.models import (
    CostCenter,
    CostCenterObligo,
    CostCenterTrueYearlySpending,
    CostCenterYearEstimate,
    WBSElement,
    WBSElementObligo,
    WBSElementTrueYearlySpending,
    WBSElementYearEstimate,
)
from apps.finances.psp_cost_types import PSP_COST_TYPE_AMOUNT_FIELDS
from apps.finances.views.psp_crud import PSPCreateView, PSPDeleteView, PSPListView, PSPUpdateView
from apps.hr.models import Employee, FundingAllocation, Workgroup


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

    def test_third_party_funding_commitment_accepts_long_filename(self):
        """Regression: long client filenames must not break PSP save."""
        from apps.core.models import StoredFile

        field_max = WBSElement._meta.get_field('third_party_funding_commitment').max_length
        # Client name within form limit; storage path (prefix + name) exceeds max_length.
        long_name = ('x' * 230) + '.pdf'
        self.assertLessEqual(len(long_name), field_max)
        self.assertGreater(
            len('finances/psp/third_party_funding/2026/07/' + long_name),
            field_max,
        )
        pdf = SimpleUploadedFile(long_name, b'%PDF-1.4 long', content_type='application/pdf')
        form = WBSElementForm(
            data={
                'wbs_code': 'D-999.0002.4',
                'title': 'Long funding file name',
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
        self.assertLessEqual(len(psp.third_party_funding_commitment.name), field_max)
        self.assertTrue(psp.third_party_funding_commitment.name.endswith('.pdf'))
        stored = StoredFile.objects.get(name=psp.third_party_funding_commitment.name)
        self.assertEqual(stored.original_filename, long_name)


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
            for field in PSP_COST_TYPE_AMOUNT_FIELDS:
                data[f'{prefix}-{field}'] = row.get(field, '')
            data[f'{prefix}-id'] = row.get('id', '')
            data[f'{prefix}-DELETE'] = row.get('DELETE', '')
        return data

    def test_duplicate_year_blocks_save(self):
        formset = WBSElementYearEstimateFormSet(
            self._formset_data([
                {'year': '2026', 'material_costs': '1000.00'},
                {'year': '2026', 'material_costs': '2000.00'},
            ]),
            instance=self.psp,
        )
        self.assertFalse(formset.is_valid())
        self.assertTrue(formset.non_form_errors)

    def test_unique_years_save_successfully(self):
        formset = WBSElementYearEstimateFormSet(
            self._formset_data([
                {'year': '2026', 'material_costs': '1000.00'},
                {'year': '2027', 'personnel_costs': '1500.00'},
            ]),
            instance=self.psp,
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.psp.year_estimates.count(), 2)
        estimate_2026 = WBSElementYearEstimate.objects.get(wbs_element=self.psp, year=2026)
        self.assertEqual(estimate_2026.material_costs, 1000.00)

    def test_cost_type_flags_default_false_and_can_enable(self):
        self.assertFalse(self.psp.has_material_costs)
        form = WBSElementForm(
            data={
                'wbs_code': self.psp.wbs_code,
                'title': self.psp.title,
                'work_group': '',
                'responsible_person': '',
                'cost_center': self.cost_center.pk,
                'period_start': '',
                'period_end': '',
                'subject_to_annual_recurrence': False,
                'is_inactive': False,
                'comment': '',
                'third_party_funder_identifier': '',
                'has_material_costs': True,
                'has_personnel_costs': True,
            },
            instance=self.psp,
        )
        self.assertTrue(form.is_valid(), form.errors)
        psp = form.save()
        self.assertTrue(psp.has_material_costs)
        self.assertTrue(psp.has_personnel_costs)
        self.assertFalse(psp.has_domestic_travel_costs)

    def test_clear_disabled_year_estimate_amounts(self):
        from apps.finances.psp_cost_types import clear_disabled_year_estimate_amounts

        self.psp.has_material_costs = True
        self.psp.has_personnel_costs = False
        self.psp.save()
        estimate = WBSElementYearEstimate.objects.create(
            wbs_element=self.psp,
            year=2026,
            material_costs=500,
            personnel_costs=900,
        )
        clear_disabled_year_estimate_amounts(self.psp)
        estimate.refresh_from_db()
        self.assertEqual(estimate.material_costs, 500)
        self.assertIsNone(estimate.personnel_costs)


class WBSElementTrueYearlySpendingTests(TestCase):
    def setUp(self):
        self.cost_center = CostCenter.objects.create(cost_center='SPEND/2026')
        self.psp = WBSElement.objects.create(
            wbs_code='D-888.0001.1',
            title='Spending test',
            cost_center=self.cost_center,
        )

    def test_stores_actual_amounts_independently_of_estimates(self):
        WBSElementYearEstimate.objects.create(
            wbs_element=self.psp,
            year=2026,
            material_costs=1000,
        )
        spending = WBSElementTrueYearlySpending.objects.create(
            wbs_element=self.psp,
            date_of_update=date(2026, 6, 15),
            material_costs=750,
            personnel_costs=200,
        )
        self.assertEqual(self.psp.true_yearly_spendings.count(), 1)
        self.assertEqual(spending.material_costs, 750)
        self.assertEqual(spending.date_of_update, date(2026, 6, 15))
        self.assertEqual(self.psp.year_estimates.get(year=2026).material_costs, 1000)

    def test_unique_per_psp_and_date_of_update(self):
        from django.db import IntegrityError, transaction

        WBSElementTrueYearlySpending.objects.create(
            wbs_element=self.psp,
            date_of_update=date(2026, 6, 15),
            material_costs=100,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WBSElementTrueYearlySpending.objects.create(
                    wbs_element=self.psp,
                    date_of_update=date(2026, 6, 15),
                    material_costs=200,
                )

    def test_internal_service_charges_amount_field(self):
        spending = WBSElementTrueYearlySpending.objects.create(
            wbs_element=self.psp,
            date_of_update=date(2026, 7, 1),
            internal_service_charges=123.45,
        )
        self.assertEqual(spending.internal_service_charges, 123.45)

    def test_obligo_snapshot(self):
        obligo = WBSElementObligo.objects.create(
            wbs_element=self.psp,
            date_of_update=date(2026, 7, 10),
            material_costs=50,
            internal_service_charges=10,
        )
        self.assertEqual(self.psp.obligos.count(), 1)
        self.assertEqual(obligo.material_costs, 50)
        self.assertEqual(str(obligo), f'{self.psp.wbs_code} — 2026-07-10 (obligo)')


class CostCenterFormTests(TestCase):
    def test_valid_form_saves(self):
        form = CostCenterForm(data={
            'cost_center': '4711/2028',
            'comments': 'Test comments',
            'has_material_costs': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        cc = form.save()
        self.assertEqual(cc.cost_center, '4711/2028')
        self.assertTrue(cc.has_material_costs)
        self.assertFalse(cc.has_personnel_costs)

    def test_checkbox_labels_omit_leading_numbers(self):
        form = CostCenterForm()
        label = str(form.fields['has_material_costs'].label)
        self.assertIn('Sachkosten', label)
        self.assertNotIn('.1', label)


class PSPManageAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        assign_permissions_to_groups()

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
        self.psp_group_a = WBSElement.objects.create(
            wbs_code='WBS-A-1',
            title='Group A PSP',
            cost_center=self.cost_center,
            work_group=self.workgroup_a,
        )
        self.psp_group_b = WBSElement.objects.create(
            wbs_code='WBS-B-1',
            title='Group B PSP',
            cost_center=self.cost_center,
            work_group=self.workgroup_b,
        )

        self.group_manager = CustomUser.objects.create_user('psp-group-manager', password='test')
        self.group_manager.password_changed = True
        self.group_manager.save(update_fields=['password_changed'])
        self.group_manager.groups.add(Group.objects.get(name=GroupNames.PSP_ELEMENTS_MANAGE))
        self.group_employee = Employee.objects.create(
            employee_number='E-PSP-MGR',
            first_name='Manager',
            last_name='User',
            user=self.group_manager,
        )
        self.workgroup_a.members.add(self.group_employee)

        self.assisting_admin = CustomUser.objects.create_user('psp-assisting-admin', password='test')
        self.assisting_admin.password_changed = True
        self.assisting_admin.save(update_fields=['password_changed'])
        self.assisting_admin.groups.add(Group.objects.get(name=GroupNames.ASSISTING_ADMINS))

    def test_group_manager_only_sees_own_workgroup_psp_elements(self):
        factory = RequestFactory()
        request = factory.get('/finances/psp/manage/')
        request.user = self.group_manager

        view = PSPListView()
        view.request = request
        queryset = view.get_queryset()

        self.assertEqual(list(queryset), [self.psp_group_a])

    def test_group_manager_cannot_edit_other_workgroup_psp(self):
        factory = RequestFactory()
        request = factory.get(f'/finances/psp/manage/{self.psp_group_b.pk}/edit/')
        request.user = self.group_manager

        view = PSPUpdateView()
        view.setup(request, pk=self.psp_group_b.pk)
        with self.assertRaises(Http404):
            view.get_object()

    def test_group_manager_edit_form_loads_own_psp_values(self):
        factory = RequestFactory()
        request = factory.get(f'/finances/psp/manage/{self.psp_group_a.pk}/edit/')
        request.user = self.group_manager

        view = PSPUpdateView()
        view.setup(request, pk=self.psp_group_a.pk)
        view.object = view.get_object()
        form = view.get_form()

        self.assertFalse(form.is_bound)
        self.assertEqual(form['wbs_code'].value(), 'WBS-A-1')
        self.assertEqual(form['title'].value(), 'Group A PSP')
        self.assertEqual(form['work_group'].value(), self.workgroup_a.pk)

    def test_group_manager_create_hides_work_group_and_prefills_value(self):
        factory = RequestFactory()
        request = factory.get('/finances/psp/manage/new/')
        request.user = self.group_manager

        view = PSPCreateView()
        view.setup(request)
        view.object = None
        form = view.get_form()
        context = view.get_context_data()

        self.assertTrue(context['hide_work_group_field'])
        self.assertEqual(form.fields['work_group'].widget.__class__.__name__, 'HiddenInput')
        self.assertEqual(form['work_group'].value(), self.workgroup_a.pk)

    def test_assisting_admin_can_edit_other_workgroup_psp(self):
        factory = RequestFactory()
        request = factory.get(f'/finances/psp/manage/{self.psp_group_b.pk}/edit/')
        request.user = self.assisting_admin

        response = PSPUpdateView.as_view()(request, pk=self.psp_group_b.pk)
        response.render()
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('WBS-B-1', content)
        self.assertIn('Group B PSP', content)
        self.assertIn('Work group', content)

    def test_delete_protected_psp_returns_redirect_not_server_error(self):
        allocation_employee = Employee.objects.create(
            employee_number='E-ALLOC',
            first_name='Alloc',
            last_name='User',
        )
        FundingAllocation.objects.create(
            employee=allocation_employee,
            wbs_element=self.psp_group_a,
            workhours_percentage='25.00',
            start_date=date(2026, 1, 1),
        )

        client = Client()
        client.login(username='psp-group-manager', password='test')
        response = client.post(f'/finances/psp/manage/{self.psp_group_a.pk}/delete/')

        self.assertEqual(response.status_code, 302)
        self.assertTrue(WBSElement.objects.filter(pk=self.psp_group_a.pk).exists())

    def test_delete_confirm_shows_blockers_for_protected_psp(self):
        allocation_employee = Employee.objects.create(
            employee_number='E-ALLOC2',
            first_name='Alloc',
            last_name='Two',
        )
        FundingAllocation.objects.create(
            employee=allocation_employee,
            wbs_element=self.psp_group_a,
            workhours_percentage='15.00',
            start_date=date(2026, 1, 1),
        )

        client = Client()
        client.login(username='psp-group-manager', password='test')
        response = client.get(f'/finances/psp/manage/{self.psp_group_a.pk}/delete/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cannot be deleted yet')
        self.assertContains(response, 'funding allocation')
        self.assertContains(response, 'Cannot delete')

    def test_delete_without_dependencies_shows_success_message(self):
        client = Client()
        client.login(username='psp-group-manager', password='test')
        response = client.post(
            f'/finances/psp/manage/{self.psp_group_a.pk}/delete/',
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WBSElement.objects.filter(pk=self.psp_group_a.pk).exists())
        self.assertContains(response, 'was deleted')


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
            for field in PSP_COST_TYPE_AMOUNT_FIELDS:
                data[f'{prefix}-{field}'] = row.get(field, '')
            data[f'{prefix}-id'] = row.get('id', '')
            data[f'{prefix}-DELETE'] = row.get('DELETE', '')
        return data

    def test_unique_years_save_with_lomv_and_cost_types(self):
        formset = CostCenterYearEstimateFormSet(
            self._formset_data([
                {'year': '2026', 'lomv': '3000.00', 'material_costs': '100.00'},
                {'year': '2027', 'lomv': '3500.00', 'personnel_costs': '200.00'},
            ]),
            instance=self.cost_center,
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.cost_center.year_estimates.count(), 2)
        estimate = self.cost_center.year_estimates.get(year=2026)
        self.assertEqual(estimate.lomv, 3000.00)
        self.assertEqual(estimate.material_costs, 100.00)

    def test_clear_disabled_amounts_keeps_lomv(self):
        from apps.finances.psp_cost_types import clear_disabled_year_estimate_amounts

        self.cost_center.has_material_costs = True
        self.cost_center.has_personnel_costs = False
        self.cost_center.save()
        estimate = CostCenterYearEstimate.objects.create(
            cost_center=self.cost_center,
            year=2026,
            lomv=5000,
            material_costs=100,
            personnel_costs=200,
        )
        clear_disabled_year_estimate_amounts(self.cost_center)
        estimate.refresh_from_db()
        self.assertEqual(estimate.lomv, 5000)
        self.assertEqual(estimate.material_costs, 100)
        self.assertIsNone(estimate.personnel_costs)


class CostCenterTrueYearlySpendingTests(TestCase):
    def setUp(self):
        self.cost_center = CostCenter.objects.create(cost_center='TRUE/2026')

    def test_stores_independently_of_estimates(self):
        CostCenterYearEstimate.objects.create(
            cost_center=self.cost_center,
            year=2026,
            lomv=1000,
            material_costs=500,
        )
        spending = CostCenterTrueYearlySpending.objects.create(
            cost_center=self.cost_center,
            date_of_update=date(2026, 6, 1),
            material_costs=400,
        )
        self.assertEqual(self.cost_center.true_yearly_spendings.count(), 1)
        self.assertEqual(spending.material_costs, 400)
        self.assertEqual(spending.date_of_update, date(2026, 6, 1))
        self.assertEqual(self.cost_center.year_estimates.get(year=2026).lomv, 1000)

    def test_obligo_and_internal_service_charges(self):
        obligo = CostCenterObligo.objects.create(
            cost_center=self.cost_center,
            date_of_update=date(2026, 7, 20),
            internal_service_charges=99.50,
        )
        self.assertEqual(self.cost_center.obligos.count(), 1)
        self.assertEqual(obligo.internal_service_charges, 99.50)
