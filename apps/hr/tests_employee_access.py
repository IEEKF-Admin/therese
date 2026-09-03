"""Workgroup-scoped vs institute-wide employee access."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import assign_permissions_to_groups, get_or_create_default_groups
from apps.hr.employee_access import (
    filter_employees_for_user,
    user_can_manage_employee,
    user_can_view_employee,
)
from apps.hr.forms import EmployeeForm, EmployeeProfileForm
from apps.hr.models import Contract, Employee, Workgroup


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(Employee)
    for code in codenames:
        perm = Permission.objects.get(content_type=ct, codename=code)
        user.user_permissions.add(perm)


def _ready_user(username):
    """Create a user that can pass force-password-change middleware."""
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class EmployeeAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.pi = Employee.objects.create(
            employee_number='PI1', first_name='Principal', last_name='Investigator',
        )
        self.wg_a = Workgroup.objects.create(
            short_name='WG-A', long_name='Group A', pi=self.pi,
        )
        self.wg_b = Workgroup.objects.create(
            short_name='WG-B', long_name='Group B', pi=self.pi,
        )

        self.viewer = _ready_user('viewer')
        self.viewer_emp = Employee.objects.create(
            employee_number='V1', first_name='View', last_name='Er', user=self.viewer,
        )
        self.wg_a.members.add(self.viewer_emp)
        _grant(self.viewer, 'can_view_employees')

        self.manager = _ready_user('manager')
        self.manager_emp = Employee.objects.create(
            employee_number='M1', first_name='Man', last_name='Ager', user=self.manager,
        )
        self.wg_a.members.add(self.manager_emp)
        _grant(self.manager, 'can_view_employees', 'manage_employee')

        self.global_mgr = _ready_user('global')
        _grant(
            self.global_mgr,
            'can_view_employees',
            'manage_employee',
            'can_view_all_employees',
            'manage_all_employees',
        )

        self.emp_a = Employee.objects.create(
            employee_number='A1', first_name='In', last_name='A',
        )
        self.wg_a.members.add(self.emp_a)

        self.emp_b = Employee.objects.create(
            employee_number='B1', first_name='In', last_name='B',
        )
        self.wg_b.members.add(self.emp_b)

    def test_view_scoped_to_shared_workgroup(self):
        qs = filter_employees_for_user(Employee.objects.all(), self.viewer)
        pks = set(qs.values_list('pk', flat=True))
        self.assertIn(self.emp_a.pk, pks)
        self.assertNotIn(self.emp_b.pk, pks)
        self.assertTrue(user_can_view_employee(self.viewer, self.emp_a))
        self.assertFalse(user_can_view_employee(self.viewer, self.emp_b))

    def test_manage_scoped(self):
        self.assertTrue(user_can_manage_employee(self.manager, self.emp_a))
        self.assertFalse(user_can_manage_employee(self.manager, self.emp_b))
        self.assertFalse(user_can_manage_employee(self.viewer, self.emp_a))

    def test_institute_wide_manage(self):
        self.assertTrue(user_can_view_employee(self.global_mgr, self.emp_a))
        self.assertTrue(user_can_view_employee(self.global_mgr, self.emp_b))
        self.assertTrue(user_can_manage_employee(self.global_mgr, self.emp_b))

    def test_employee_list_partial_search(self):
        client = Client()
        client.login(username='viewer', password='test')
        response = client.get('/hr/employees/', {'q': 'View', 'partial': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('View', response.content.decode())
        self.assertNotIn('<html', response.content.decode().lower())

    def test_list_view_respects_scope(self):
        client = Client()
        client.login(username='viewer', password='test')
        resp = client.get('/hr/employees/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('A1', content)
        self.assertNotIn('B1', content)

    def test_unauth_edit_redirects_to_login_with_edit_next(self):
        from urllib.parse import parse_qs, urlparse

        url = f'/hr/employees/{self.emp_a.pk}/edit/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        parsed = urlparse(response.url)
        self.assertTrue(parsed.path.endswith('/accounts/login/'))
        self.assertEqual(parse_qs(parsed.query).get('next', [''])[0], url)
        follow = self.client.get(url, follow=True)
        self.assertNotIn(
            "You don't have permission to edit this employee.",
            follow.content.decode(),
        )

    def test_edit_blocked_outside_workgroup(self):
        client = Client()
        client.login(username='manager', password='test')
        resp = client.get(f'/hr/employees/{self.emp_b.pk}/edit/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/hr/employees/', resp.url)

    def test_no_workgroup_sees_none_when_scoped(self):
        lone = CustomUser.objects.create_user('lone', password='test')
        Employee.objects.create(
            employee_number='L1', first_name='Lone', last_name='User', user=lone,
        )
        _grant(lone, 'can_view_employees', 'manage_employee')
        qs = filter_employees_for_user(Employee.objects.all(), lone)
        self.assertEqual(qs.count(), 0)


class EmployeeFormCheckNeededTests(TestCase):
    def test_linked_user_with_check_needed_shows_form_error_not_500(self):
        login = CustomUser.objects.create_user('linked', password='test')
        employee = Employee.objects.create(
            employee_number='CN-1',
            first_name='Check',
            last_name='Needed',
            user=login,
            check_needed=True,
        )
        form = EmployeeForm(
            data={
                'employee_number': employee.employee_number,
                'first_name': 'Check',
                'last_name': 'Needed',
                'check_needed': 'on',
            },
            instance=employee,
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)
        self.assertNotIn('user', form.errors)


class ArchivedContractEmployeeSaveTests(TestCase):
    def setUp(self):
        get_or_create_default_groups()
        assign_permissions_to_groups()
        self.user = _ready_user('hr-arch')
        _grant(self.user, 'manage_all_employees', 'manage_employee')
        self.employee = Employee.objects.create(
            employee_number='ARCH-1',
            first_name='Archived',
            last_name='Only',
            gender='X',
            country='Germany',
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2020, 1, 1),
            valid_until=date(2024, 12, 31),
            is_active=False,
        )

    def test_save_succeeds_without_posted_funding_formset(self):
        self.client.login(username='hr-arch', password='test')
        response = self.client.post(
            reverse('hr:employee_update', args=[self.employee.pk]),
            {
                'employee_number': 'ARCH-1',
                'first_name': 'Archived',
                'last_name': 'Only',
                'gender': 'X',
                'country': 'Germany',
                'contracts-TOTAL_FORMS': '1',
                'contracts-INITIAL_FORMS': '1',
                'contracts-MIN_NUM_FORMS': '0',
                'contracts-MAX_NUM_FORMS': '1000',
                'contracts-0-id': str(self.contract.pk),
                'contracts-0-weekly_hours': '39.000',
                'contracts-0-valid_from': '01.01.2020',
                'contracts-0-valid_until': '31.12.2024',
                'Workgroup_members-TOTAL_FORMS': '0',
                'Workgroup_members-INITIAL_FORMS': '0',
                'Workgroup_members-MIN_NUM_FORMS': '0',
                'Workgroup_members-MAX_NUM_FORMS': '1000',
            },
        )
        self.assertIn(response.status_code, (302, 303), getattr(response, 'context', None))


class ContractArchiveAndDeleteTests(TestCase):
    def setUp(self):
        get_or_create_default_groups()
        assign_permissions_to_groups()
        self.admin = _ready_user('sysadmin')
        from apps.accounts.permissions import GroupNames
        from django.contrib.auth.models import Group
        Group.objects.get_or_create(name=GroupNames.SYSTEMADMIN)[0].user_set.add(self.admin)
        _grant(self.admin, 'manage_all_employees', 'manage_employee')
        self.employee = Employee.objects.create(
            employee_number='DEL-1', first_name='Del', last_name='Ete',
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('20.000'),
            valid_from=date(2024, 1, 1),
            is_active=True,
            check_needed=False,
        )

    def test_archiving_clears_check_needed(self):
        self.contract.check_needed = True
        self.contract.save()
        self.contract.is_active = False
        self.contract.save()
        self.contract.refresh_from_db()
        self.assertFalse(self.contract.is_active)
        self.assertFalse(self.contract.check_needed)

    def test_employee_edit_has_no_nested_delete_forms(self):
        self.client.login(username='sysadmin', password='test')
        response = self.client.get(
            reverse('hr:employee_update', args=[self.employee.pk]),
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('form="employee-edit-form"', html)
        self.assertNotIn('method="post" action="', html.split('id="employee-edit-form"', 1)[-1].split('</form>', 1)[0])

    def test_systemadmin_can_hard_delete_contract(self):
        self.client.login(username='sysadmin', password='test')
        response = self.client.post(
            reverse('hr:contract_hard_delete', args=[self.employee.pk, self.contract.pk]),
        )
        self.assertIn(response.status_code, (302, 303))
        self.assertFalse(Contract.objects.filter(pk=self.contract.pk).exists())

    def test_restore_from_archive_reactivates_expired_contract(self):
        self.contract.valid_from = date(2020, 1, 1)
        self.contract.valid_until = date(2020, 12, 31)
        self.contract.is_active = False
        self.contract.save()
        self.client.login(username='sysadmin', password='test')
        response = self.client.post(
            reverse('hr:employee_list') + '?archive=1',
            {'restore_id': str(self.employee.pk)},
        )
        self.assertIn(response.status_code, (302, 303))
        self.contract.refresh_from_db()
        self.assertTrue(self.contract.is_active)
        self.assertIsNone(self.contract.valid_until)
        active = self.client.get(reverse('hr:employee_list'))
        self.assertContains(active, 'Del Ete')
        archived = self.client.get(reverse('hr:employee_list'), {'archive': '1'})
        self.assertNotContains(archived, 'Del Ete')

    def test_non_sysadmin_cannot_hard_delete_contract(self):
        other = _ready_user('hruser')
        _grant(other, 'manage_all_employees', 'manage_employee')
        self.client.login(username='hruser', password='test')
        response = self.client.post(
            reverse('hr:contract_hard_delete', args=[self.employee.pk, self.contract.pk]),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())


class EmployeeProfileFormTests(TestCase):
    def test_profile_save_keeps_existing_employee_number(self):
        user = CustomUser.objects.create_user('selfuser', password='test')
        user.password_changed = True
        user.save(update_fields=['password_changed'])
        employee = Employee.objects.create(
            employee_number='P-84',
            first_name='Self',
            last_name='User',
            gender='X',
            country='Germany',
            user=user,
        )
        form = EmployeeProfileForm(
            data={
                'country': 'Germany',
                'email_professional': 'self@example.org',
            },
            instance=employee,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.employee_number, 'P-84')

    def test_my_profile_post_succeeds_without_employee_number_field(self):
        user = _ready_user('selfuser2')
        Employee.objects.create(
            employee_number='P-85',
            first_name='Self',
            last_name='Two',
            gender='X',
            country='Germany',
            user=user,
        )
        self.client.login(username='selfuser2', password='test')
        response = self.client.post(
            reverse('hr:my_profile'),
            {
                'country': 'Germany',
                'email_professional': 'two@example.org',
                'Workgroup_members-TOTAL_FORMS': '0',
                'Workgroup_members-INITIAL_FORMS': '0',
                'Workgroup_members-MIN_NUM_FORMS': '0',
                'Workgroup_members-MAX_NUM_FORMS': '1000',
            },
        )
        self.assertIn(response.status_code, (302, 303), getattr(response, 'context', None))


class NewContractFundingTemplateTests(TestCase):
    def setUp(self):
        get_or_create_default_groups()
        assign_permissions_to_groups()
        self.user = _ready_user('hr-fa')
        _grant(self.user, 'manage_all_employees', 'manage_employee')
        self.employee = Employee.objects.create(
            employee_number='FA-1',
            first_name='Fund',
            last_name='Ing',
            gender='X',
            country='Germany',
        )

    def test_invalid_funding_total_keeps_add_funding_template(self):
        self.client.login(username='hr-fa', password='test')
        response = self.client.post(
            reverse('hr:employee_update', args=[self.employee.pk]),
            {
                'employee_number': 'FA-1',
                'first_name': 'Fund',
                'last_name': 'Ing',
                'gender': 'X',
                'country': 'Germany',
                'contracts-TOTAL_FORMS': '1',
                'contracts-INITIAL_FORMS': '0',
                'contracts-MIN_NUM_FORMS': '0',
                'contracts-MAX_NUM_FORMS': '1000',
                'contracts-0-weekly_hours': '39.000',
                'contracts-0-valid_from': '01.01.2026',
                'contracts-0-is_active': 'on',
                'fa_n0-TOTAL_FORMS': '0',
                'fa_n0-INITIAL_FORMS': '0',
                'fa_n0-MIN_NUM_FORMS': '0',
                'fa_n0-MAX_NUM_FORMS': '1000',
                'ss_n0-TOTAL_FORMS': '0',
                'ss_n0-INITIAL_FORMS': '0',
                'ss_n0-MIN_NUM_FORMS': '0',
                'ss_n0-MAX_NUM_FORMS': '1000',
                'Workgroup_members-TOTAL_FORMS': '0',
                'Workgroup_members-INITIAL_FORMS': '0',
                'Workgroup_members-MIN_NUM_FORMS': '0',
                'Workgroup_members-MAX_NUM_FORMS': '1000',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get('empty_funding_form'))
        self.assertContains(response, 'id="funding-empty-template"')
        self.assertContains(response, 'funding-item')
        self.assertContains(response, 'btn-add-funding')
