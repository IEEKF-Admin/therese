"""Workgroup-scoped vs institute-wide employee access."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase

from apps.accounts.models import CustomUser
from apps.accounts.permissions import assign_permissions_to_groups, get_or_create_default_groups
from apps.hr.employee_access import (
    filter_employees_for_user,
    user_can_manage_employee,
    user_can_view_employee,
)
from apps.hr.models import Employee, Workgroup


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

    def test_list_view_respects_scope(self):
        client = Client()
        client.login(username='viewer', password='test')
        resp = client.get('/hr/employees/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('A1', content)
        self.assertNotIn('B1', content)

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
