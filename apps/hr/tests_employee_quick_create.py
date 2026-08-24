"""Minimal employee create form used from personnel reallocation."""

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.core.models import GlobalSetting
from apps.hr.models import Employee, Workgroup


def _ready_user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class MinimalEmployeeCreateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.pi = Employee.objects.create(
            employee_number='PI-Q', first_name='Pat', last_name='PI',
        )
        self.wg_a = Workgroup.objects.create(
            short_name='Quick-A', long_name='Quick A', pi=self.pi,
        )
        self.wg_b = Workgroup.objects.create(
            short_name='Quick-B', long_name='Quick B', pi=self.pi,
        )

        self.manager = _ready_user('quick-mgr')
        self.manager.groups.add(Group.objects.get(name=GroupNames.EMPLOYEES_MANAGE))
        self.manager_emp = Employee.objects.create(
            employee_number='QM1', first_name='Man', last_name='Ager', user=self.manager,
        )
        self.wg_b.members.add(self.manager_emp)
        self.wg_a.members.add(self.manager_emp)

        self.all_mgr = _ready_user('quick-all')
        self.all_mgr.groups.add(Group.objects.get(name=GroupNames.EMPLOYEES_MANAGE_ALL))
        Employee.objects.create(
            employee_number='QA1', first_name='All', last_name='Manager', user=self.all_mgr,
        )

        self.other = _ready_user('quick-other')
        Employee.objects.create(
            employee_number='QO1', first_name='No', last_name='Rights', user=self.other,
        )

        self.client = Client()

    def test_forbidden_without_manage_permission(self):
        self.client.login(username='quick-other', password='test')
        response = self.client.get(reverse('hr:employee_quick_create'))
        self.assertEqual(response.status_code, 403)

    def test_scoped_manager_hides_workgroup_and_assigns_first(self):
        self.client.login(username='quick-mgr', password='test')
        get_resp = self.client.get(reverse('hr:employee_quick_create'))
        self.assertEqual(get_resp.status_code, 200)
        self.assertNotContains(get_resp, 'name="work_group"')

        post_resp = self.client.post(
            reverse('hr:employee_quick_create'),
            {
                'employee_number': 'Q-NEW-1',
                'first_name': 'New',
                'last_name': 'Person',
            },
        )
        self.assertEqual(post_resp.status_code, 302)
        created = Employee.objects.get(employee_number='Q-NEW-1')
        # First workgroup by short_name among the user's groups: Quick-A before Quick-B.
        self.assertEqual(list(created.workgroups.values_list('short_name', flat=True)), ['Quick-A'])
        self.assertIn(f'employee={created.pk}', post_resp.url)

    def test_manage_all_group_requires_workgroup_choice(self):
        self.client.login(username='quick-all', password='test')
        get_resp = self.client.get(reverse('hr:employee_quick_create'))
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, 'name="work_group"')

        missing = self.client.post(
            reverse('hr:employee_quick_create'),
            {
                'employee_number': 'Q-NEW-2',
                'first_name': 'Needs',
                'last_name': 'Group',
            },
        )
        self.assertEqual(missing.status_code, 200)
        self.assertFalse(Employee.objects.filter(employee_number='Q-NEW-2').exists())

        ok = self.client.post(
            reverse('hr:employee_quick_create'),
            {
                'employee_number': 'Q-NEW-2',
                'first_name': 'Needs',
                'last_name': 'Group',
                'work_group': self.wg_b.pk,
            },
        )
        self.assertEqual(ok.status_code, 302)
        created = Employee.objects.get(employee_number='Q-NEW-2')
        self.assertEqual(list(created.workgroups.values_list('pk', flat=True)), [self.wg_b.pk])

    def test_redirect_preserves_reallocation_next_and_sets_employee(self):
        self.client.login(username='quick-mgr', password='test')
        next_url = reverse('tasks:task_create') + '?type=personnel_reallocation'
        response = self.client.post(
            reverse('hr:employee_quick_create') + '?next=' + next_url,
            {
                'employee_number': 'Q-NEW-3',
                'first_name': 'Back',
                'last_name': 'ToTask',
                'next': next_url,
            },
        )
        created = Employee.objects.get(employee_number='Q-NEW-3')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('tasks:task_create')))
        self.assertIn('type=personnel_reallocation', response.url)
        self.assertIn(f'employee={created.pk}', response.url)


class ReallocationAddEmployeeButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.user = _ready_user('realloc-btn')
        self.user.groups.add(Group.objects.get(name=GroupNames.EMPLOYEES_MANAGE))
        self.user.groups.add(Group.objects.get(name=GroupNames.PERSONNEL_TASKS_CREATE))
        Employee.objects.create(
            employee_number='RB1', first_name='Re', last_name='Alloc', user=self.user,
        )
        self.client = Client()
        GlobalSetting.objects.filter(pk=1).delete()
        GlobalSetting.objects.create(pk=1, show_add_employee_on_reallocation=True)

    def test_button_shown_when_setting_enabled(self):
        self.client.login(username='realloc-btn', password='test')
        response = self.client.get(reverse('tasks:task_create') + '?type=personnel_reallocation')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add new Employee')
        self.assertContains(response, reverse('hr:employee_quick_create'))

    def test_button_hidden_when_setting_disabled(self):
        GlobalSetting.objects.filter(pk=1).update(show_add_employee_on_reallocation=False)
        self.client.login(username='realloc-btn', password='test')
        response = self.client.get(reverse('tasks:task_create') + '?type=personnel_reallocation')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Add new Employee')
