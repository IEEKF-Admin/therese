from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.hr.models import Contract, Employee
from apps.tasks.change_working_hours_apply import (
    ApplyWorkingHoursError,
    apply_change_working_hours,
)
from apps.tasks.forms import PersonnelChangeWorkingHoursTaskForm
from apps.tasks.models import PersonnelChangeWorkingHoursTask, Task


class ChangeWorkingHoursFormTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('hr', password='test')
        self.employee = Employee.objects.create(
            employee_number='E-CWH-1',
            first_name='Max',
            last_name='Hours',
            user=self.user,
        )

    def test_accepts_comma_decimal_hours(self):
        form = PersonnelChangeWorkingHoursTaskForm(
            data={
                'employee': self.employee.pk,
                'valid_from': '01.09.2026',
                'valid_until': '',
                'new_weekly_hours': '19,625',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['new_weekly_hours'], Decimal('19.625'))

    def test_rejects_zero_hours(self):
        form = PersonnelChangeWorkingHoursTaskForm(
            data={
                'employee': self.employee.pk,
                'valid_from': '01.09.2026',
                'new_weekly_hours': '0',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('new_weekly_hours', form.errors)


class ChangeWorkingHoursApplyTests(TestCase):
    def setUp(self):
        self.creator = Employee.objects.create(
            employee_number='E-CWH-CRE',
            first_name='Creator',
            last_name='User',
        )
        self.person = Employee.objects.create(
            employee_number='E-CWH-EMP',
            first_name='Target',
            last_name='Person',
        )
        self.contract = Contract.objects.create(
            employee=self.person,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2025, 1, 1),
            is_active=True,
        )
        self.task = PersonnelChangeWorkingHoursTask.objects.create(
            task_type='personnel_change_working_hours',
            creator=self.creator,
            employee=self.person,
            valid_from=date(2026, 9, 1),
            new_weekly_hours=Decimal('19.625'),
        )
        self.task.status = 'completed'
        self.task.save(update_fields=['status'])

    def test_apply_writes_hours_on_todays_contract(self):
        apply_change_working_hours(self.task)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.weekly_hours, Decimal('19.625'))

    def test_apply_fails_without_contract(self):
        self.contract.delete()
        with self.assertRaises(ApplyWorkingHoursError):
            apply_change_working_hours(self.task)


class ChangeWorkingHoursViewTests(TestCase):
    password = 'secret'

    def setUp(self):
        self.user = CustomUser.objects.create_user('approver', password=self.password)
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        perm = Permission.objects.get(
            codename='approve_personnel_task',
            content_type=ContentType.objects.get_for_model(Task),
        )
        self.user.user_permissions.add(perm)
        self.approver = Employee.objects.create(
            employee_number='E-CWH-APR',
            first_name='Ann',
            last_name='Approver',
            user=self.user,
        )
        self.person = Employee.objects.create(
            employee_number='E-CWH-TGT',
            first_name='Target',
            last_name='Employee',
        )
        self.contract = Contract.objects.create(
            employee=self.person,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2025, 1, 1),
            is_active=True,
        )
        self.task = PersonnelChangeWorkingHoursTask.objects.create(
            task_type='personnel_change_working_hours',
            creator=self.approver,
            assignee=self.approver,
            employee=self.person,
            valid_from=date(2026, 9, 1),
            new_weekly_hours=Decimal('20.000'),
        )

    def test_save_and_apply_requires_completed(self):
        self.client.login(username='approver', password=self.password)
        response = self.client.post(
            reverse('tasks:task_detail', args=[self.task.pk]),
            {
                'save_and_apply': '1',
                'status': 'sent_to_hr',
                'valid_from': '01.09.2026',
                'new_weekly_hours': '20,000',
            },
        )
        self.assertIn(response.status_code, (302, 303))
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.weekly_hours, Decimal('39.000'))

    def test_save_and_apply_updates_contract(self):
        self.task.status = 'completed'
        self.task.save(update_fields=['status'])
        self.client.login(username='approver', password=self.password)
        response = self.client.post(
            reverse('tasks:task_detail', args=[self.task.pk]),
            {
                'save_and_apply': '1',
                'status': 'completed',
                'valid_from': '01.09.2026',
                'new_weekly_hours': '19,625',
            },
        )
        self.assertIn(response.status_code, (302, 303))
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.weekly_hours, Decimal('19.625'))
        self.task.refresh_from_db()
        self.assertEqual(self.task.new_weekly_hours, Decimal('19.625'))

    def test_approver_sees_apply_button_when_completed(self):
        self.task.status = 'completed'
        self.task.save(update_fields=['status'])
        self.client.login(username='approver', password=self.password)
        response = self.client.get(reverse('tasks:task_detail', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Save and Apply')
        self.assertTrue(response.context['apply_working_hours_enabled'])
