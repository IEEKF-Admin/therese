from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.core.models import GlobalSetting, OccupationSalaryRow, OccupationSalaryTable
from apps.core.occupation_salary import fulltime_salary_from_row, resolve_salary_table
from apps.hr.models import Contract, Employee
from apps.tasks.forms import PersonnelChangeWorkingHoursTaskForm, RecruitmentJobForm
from apps.tasks.models import RecruitmentJob


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class OccupationSalaryModelTests(TestCase):
    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'default_weekly_hours': Decimal('39.000'),
                'true_cost_multiplicator': Decimal('1.300'),
            },
        )
        self.table = OccupationSalaryTable.objects.create(name='Berufsgruppen-Tabelle 1')
        self.row = OccupationSalaryRow.objects.create(
            table=self.table,
            weekly_hours=Decimal('19.500'),
            monthly_salary=Decimal('1950.00'),
        )

    def test_fulltime_conversion(self):
        # 1950 at 19.5h → 3900 at 39h
        self.assertEqual(fulltime_salary_from_row(self.row), Decimal('3900.00'))

    def test_job_uses_table_not_tvl(self):
        job = RecruitmentJob(
            name='Special',
            salary_table=self.table,
            occupation_weekly_hours=Decimal('19.500'),
            pay_scale_group='E13',
            experience_level=3,
        )
        job.full_clean()
        self.assertEqual(job.pay_scale_group, '')
        self.assertIsNone(job.experience_level)
        self.assertEqual(job.estimated_monthly_salary, Decimal('3900.00'))
        self.assertEqual(job.get_estimated_monthly_salary(), Decimal('3900.00'))

    def test_contract_hours_must_match_table(self):
        employee = Employee.objects.create(
            employee_number='OCC-1', first_name='A', last_name='B',
            salary_table=self.table,
        )
        contract = Contract(
            employee=employee,
            weekly_hours=Decimal('20.000'),
            valid_from=date(2026, 1, 1),
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            contract.full_clean()

    def test_contract_sets_fulltime_salary_from_row(self):
        employee = Employee.objects.create(
            employee_number='OCC-2', first_name='A', last_name='B',
            salary_table=self.table,
        )
        contract = Contract(
            employee=employee,
            weekly_hours=Decimal('19.500'),
            valid_from=date(2026, 1, 1),
            is_active=True,
        )
        contract.full_clean()
        self.assertEqual(contract.monthly_salary, Decimal('3900.00'))
        self.assertEqual(contract.pay_scale_group, '')

    def test_resolve_prefers_employee_table(self):
        other = OccupationSalaryTable.objects.create(name='Berufsgruppen-Tabelle 2')
        job = RecruitmentJob.objects.create(
            name='Job table',
            salary_table=self.table,
            occupation_weekly_hours=Decimal('19.500'),
        )
        employee = Employee.objects.create(
            employee_number='OCC-3', first_name='A', last_name='B',
            job=job, salary_table=other,
        )
        self.assertEqual(resolve_salary_table(employee), other)


class OccupationSalarySettingsTests(TestCase):
    def setUp(self):
        get_or_create_default_groups()
        assign_permissions_to_groups()
        self.admin = _ready('sysadmin-occ')
        self.admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        self.client = Client()
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'default_weekly_hours': Decimal('39.00'),
                'true_cost_multiplicator': Decimal('1.300'),
                'personnel_import_tolerance': Decimal('0.0250'),
                'chemical_hazard_threshold': 'any_ghs',
            },
        )

    def test_create_table_via_global_settings(self):
        self.client.login(username='sysadmin-occ', password='test')
        url = reverse('core_settings:global_settings')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Occupational salary tables')
        posted = self.client.post(url, {
            'action': 'save_global',
            'default_weekly_hours': '39.00',
            'true_cost_multiplicator': '1.300',
            'personnel_import_tolerance': '0.0250',
            'employee_expiring_soon_days': '90',
            'chemical_hazard_threshold': 'any_ghs',
            'holiday_half_day_rounding': 'up',
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'occ_tables_present': '1',
            'occ_table_0_name': 'Berufsgruppen-Tabelle 1',
            'occ_table_0_row_0_hours': '19,5',
            'occ_table_0_row_0_pay': '1950',
        })
        self.assertEqual(posted.status_code, 302)
        table = OccupationSalaryTable.objects.get(name='Berufsgruppen-Tabelle 1')
        row = table.rows.get()
        self.assertEqual(row.weekly_hours, Decimal('19.500'))
        self.assertEqual(row.monthly_salary, Decimal('1950.00'))

    def test_save_without_marker_does_not_wipe_tables(self):
        OccupationSalaryTable.objects.create(name='Keep me')
        self.client.login(username='sysadmin-occ', password='test')
        url = reverse('core_settings:global_settings')
        posted = self.client.post(url, {
            'action': 'save_global',
            'default_weekly_hours': '39.00',
            'true_cost_multiplicator': '1.300',
            'personnel_import_tolerance': '0.0250',
            'employee_expiring_soon_days': '90',
            'chemical_hazard_threshold': 'any_ghs',
            'holiday_half_day_rounding': 'up',
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(posted.status_code, 302)
        self.assertTrue(OccupationSalaryTable.objects.filter(name='Keep me').exists())


class OccupationSalaryJobFormTests(TestCase):
    def setUp(self):
        self.table = OccupationSalaryTable.objects.create(name='Berufsgruppen-Tabelle 1')
        OccupationSalaryRow.objects.create(
            table=self.table,
            weekly_hours=Decimal('20.000'),
            monthly_salary=Decimal('2000.00'),
        )
        GlobalSetting.objects.update_or_create(
            pk=1, defaults={'default_weekly_hours': Decimal('40.000')},
        )

    def test_job_form_occupation_source(self):
        form = RecruitmentJobForm(data={
            'name': 'Tech',
            'is_active': 'on',
            'salary_source': str(self.table.pk),
            'occupation_weekly_hours': '20.000',
            'pay_scale_group': '',
            'experience_level': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        job = form.save()
        self.assertEqual(job.salary_table_id, self.table.pk)
        self.assertEqual(job.occupation_weekly_hours, Decimal('20.000'))
        self.assertEqual(job.estimated_monthly_salary, Decimal('4000.00'))
        self.assertEqual(job.pay_scale_group, '')


class OccupationSalaryEmployeeViewTests(TestCase):
    def setUp(self):
        get_or_create_default_groups()
        assign_permissions_to_groups()
        self.user = _ready('hr-occ')
        ct = ContentType.objects.get_for_model(Employee)
        self.user.user_permissions.add(
            Permission.objects.get(content_type=ct, codename='manage_all_employees'),
            Permission.objects.get(content_type=ct, codename='manage_employee'),
        )
        self.table = OccupationSalaryTable.objects.create(name='Berufsgruppen-Tabelle 1')
        OccupationSalaryRow.objects.create(
            table=self.table,
            weekly_hours=Decimal('19.500'),
            monthly_salary=Decimal('1950.00'),
        )
        self.employee = Employee.objects.create(
            employee_number='OCC-84', first_name='Therese', last_name='Test',
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2020, 1, 1),
            is_active=True,
        )
        self.client = Client()

    def test_edit_page_has_salary_table_field(self):
        self.client.login(username='hr-occ', password='test')
        response = self.client.get(reverse('hr:employee_update', args=[self.employee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Salary table')
        self.assertContains(response, 'Berufsgruppen-Tabelle 1')

    def test_save_salary_table_and_matching_hours(self):
        self.client.login(username='hr-occ', password='test')
        url = reverse('hr:employee_update', args=[self.employee.pk])
        response = self.client.post(url, {
            'employee_number': 'OCC-84',
            'first_name': 'Therese',
            'last_name': 'Test',
            'gender': 'X',
            'country': 'Germany',
            'salary_table': str(self.table.pk),
            'contracts-TOTAL_FORMS': '1',
            'contracts-INITIAL_FORMS': '1',
            'contracts-MIN_NUM_FORMS': '0',
            'contracts-MAX_NUM_FORMS': '1000',
            'contracts-0-id': str(self.contract.pk),
            'contracts-0-weekly_hours': '19.500',
            'contracts-0-valid_from': '01.01.2020',
            'contracts-0-is_active': 'on',
            'Workgroup_members-TOTAL_FORMS': '0',
            'Workgroup_members-INITIAL_FORMS': '0',
            'Workgroup_members-MIN_NUM_FORMS': '0',
            'Workgroup_members-MAX_NUM_FORMS': '1000',
        })
        self.assertIn(response.status_code, (200, 302, 303), getattr(response, 'context', None))
        self.employee.refresh_from_db()
        self.contract.refresh_from_db()
        self.assertEqual(self.employee.salary_table_id, self.table.pk)
        self.assertEqual(self.contract.weekly_hours, Decimal('19.500'))
        self.assertEqual(self.contract.monthly_salary, Decimal('3900.00'))


class OccupationChangeHoursTests(TestCase):
    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1, defaults={'default_weekly_hours': Decimal('39.000')},
        )
        self.table = OccupationSalaryTable.objects.create(name='Berufsgruppen-Tabelle 1')
        OccupationSalaryRow.objects.create(
            table=self.table, weekly_hours=Decimal('19.500'), monthly_salary=Decimal('1950.00'),
        )
        OccupationSalaryRow.objects.create(
            table=self.table, weekly_hours=Decimal('39.000'), monthly_salary=Decimal('3900.00'),
        )
        self.user = CustomUser.objects.create_user('hr', password='test')
        self.employee = Employee.objects.create(
            employee_number='OCC-CWH', first_name='Max', last_name='Hours',
            salary_table=self.table,
        )

    def test_form_rejects_hours_not_in_table(self):
        form = PersonnelChangeWorkingHoursTaskForm(
            data={
                'employee': self.employee.pk,
                'valid_from': '01.09.2026',
                'new_weekly_hours': '12.000',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('new_weekly_hours', form.errors)

    def test_form_accepts_table_hours(self):
        form = PersonnelChangeWorkingHoursTaskForm(
            data={
                'employee': self.employee.pk,
                'valid_from': '01.09.2026',
                'new_weekly_hours': '19.500',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertTrue(form.is_valid(), form.errors)
