"""Workgroup-scoped checklist progress uses all of the user's workgroups."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase

from apps.accounts.models import CustomUser
from apps.checklists.access import employees_in_user_workgroups
from apps.checklists.models import ChecklistTemplate
from apps.hr.models import Employee, Workgroup


def _ready_user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


def _grant_checklist(user, *codenames):
    ct = ContentType.objects.get_for_model(ChecklistTemplate)
    for code in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=code))


class ChecklistProgressAccessTests(TestCase):
    def setUp(self):
        self.pi_emp = Employee.objects.create(
            employee_number='PI-CL', first_name='P', last_name='I',
        )
        self.wg_a = Workgroup.objects.create(
            short_name='CL-A', long_name='CL A', pi=self.pi_emp,
        )
        self.wg_b = Workgroup.objects.create(
            short_name='CL-B', long_name='CL B', pi=self.pi_emp,
        )
        self.user = _ready_user('cl-viewer')
        self.user_emp = Employee.objects.create(
            employee_number='CL-V', first_name='View', last_name='Er', user=self.user,
        )
        self.wg_a.members.add(self.user_emp)
        self.wg_b.members.add(self.user_emp)
        _grant_checklist(self.user, 'view_checklist', 'view_workgroup_progress')

        self.emp_a = Employee.objects.create(
            employee_number='CL-A1', first_name='In', last_name='A',
        )
        self.emp_b = Employee.objects.create(
            employee_number='CL-B1', first_name='In', last_name='B',
        )
        self.emp_c = Employee.objects.create(
            employee_number='CL-C1', first_name='Out', last_name='C',
        )
        self.wg_a.members.add(self.emp_a)
        self.wg_b.members.add(self.emp_b)

        self.wg_other = Workgroup.objects.create(
            short_name='CL-X', long_name='CL X', pi=self.pi_emp,
        )
        self.wg_other.members.add(self.emp_c)

    def test_employees_from_all_user_workgroups(self):
        employees = employees_in_user_workgroups(self.user)
        pks = {e.pk for e in employees}
        self.assertIn(self.emp_a.pk, pks)
        self.assertIn(self.emp_b.pk, pks)
        self.assertIn(self.user_emp.pk, pks)
        self.assertNotIn(self.emp_c.pk, pks)

    def test_progress_view_lists_all_workgroup_members(self):
        client = Client()
        client.login(username='cl-viewer', password='test')
        resp = client.get('/checklists/progress/workgroup/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('Checklist Progress', content)
        self.assertIn('In A', content)
        self.assertIn('In B', content)
        self.assertIn('CL-A, CL-B', content)
        self.assertNotIn('Out C', content)
