from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.core.models import GlobalSetting
from apps.hr.forms import EmployeeForm
from apps.hr.models import Contract, Employee
from apps.holidays.services import create_request


def _user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class ExternalEmployeeFormTests(TestCase):
    def test_institute_requires_employee_number(self):
        form = EmployeeForm(data={
            'first_name': 'Ina',
            'last_name': 'Institute',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('employee_number', form.errors)

    def test_external_allows_empty_number(self):
        form = EmployeeForm(data={
            'first_name': 'Exa',
            'last_name': 'Ternal',
            'gender': 'X',
            'country': 'Germany',
            'is_external': 'on',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['employee_number'])

    def test_external_can_link_existing_user(self):
        login = _user('ext-login')
        form = EmployeeForm(data={
            'first_name': 'Exa',
            'last_name': 'Ternal',
            'gender': 'X',
            'country': 'Germany',
            'is_external': 'on',
            'user': str(login.pk),
        })
        self.assertTrue(form.is_valid(), form.errors)
        emp = form.save()
        self.assertTrue(emp.is_external)
        self.assertEqual(emp.user_id, login.pk)


class ExternalEmployeeListTests(TestCase):
    def setUp(self):
        self.admin = _user('hr-all')
        perm = Permission.objects.get(
            codename='can_view_all_employees',
            content_type=ContentType.objects.get_for_model(Employee),
        )
        self.admin.user_permissions.add(perm)
        Employee.objects.create(
            employee_number='HR-ALL',
            first_name='Hr',
            last_name='Admin',
            user=self.admin,
        )
        self.external = Employee.objects.create(
            first_name='Guest',
            last_name='Person',
            is_external=True,
        )
        self.institute = Employee.objects.create(
            employee_number='INST-1',
            first_name='Staff',
            last_name='Member',
        )
        Contract.objects.create(
            employee=self.institute,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2025, 1, 1),
            is_active=True,
        )

    def test_list_shows_external_badge_and_keeps_without_contract(self):
        self.client.login(username='hr-all', password='test')
        response = self.client.get(reverse('hr:employee_list'))
        self.assertEqual(response.status_code, 200)
        names = [e.get_full_name() for e in response.context['employees']]
        self.assertIn('Guest Person', names)
        self.assertContains(response, 'External')

    def test_phone_list_excludes_externals(self):
        self.client.login(username='hr-all', password='test')
        Contract.objects.create(
            employee=self.external,
            weekly_hours=Decimal('10.000'),
            valid_from=date(2025, 1, 1),
            is_active=True,
        )
        response = self.client.get(reverse('hr:phone_list'))
        self.assertEqual(response.status_code, 200)
        ids = [e.pk for e in response.context['employees']]
        self.assertNotIn(self.external.pk, ids)
        self.assertIn(self.institute.pk, ids)


class ExternalHolidayTests(TestCase):
    def setUp(self):
        setting = GlobalSetting.get_solo()
        setting.holidays_enabled = True
        setting.holidays_planning_enabled = True
        setting.save()
        self.user = _user('ext-hol')
        self.employee = Employee.objects.create(
            first_name='Ext',
            last_name='Holiday',
            is_external=True,
            user=self.user,
        )

    def test_my_holidays_forbidden(self):
        self.client.login(username='ext-hol', password='test')
        response = self.client.get(reverse('holidays:my_holidays'))
        self.assertEqual(response.status_code, 403)

    def test_create_request_rejected(self):
        with self.assertRaises(Exception):
            create_request(self.user, self.employee, [date.today()])
