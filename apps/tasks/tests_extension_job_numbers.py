from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.finances.models import WBSElement
from apps.hr.models import Contract, Employee, FundingAllocation
from apps.tasks.models import PersonnelContractExtensionTask, Task


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class ExtensionJobNumberDisplayTests(TestCase):
    def setUp(self):
        self.approver_user = _ready('ext-approver')
        self.creator_user = _ready('ext-creator')
        perm = Permission.objects.get(
            codename='approve_personnel_task',
            content_type=ContentType.objects.get_for_model(Task),
        )
        self.approver_user.user_permissions.add(perm)
        self.approver = Employee.objects.create(
            employee_number='E-EXT-APR',
            first_name='Ann',
            last_name='Approver',
            user=self.approver_user,
        )
        self.creator = Employee.objects.create(
            employee_number='E-EXT-CRE',
            first_name='Chris',
            last_name='Creator',
            user=self.creator_user,
        )
        self.person = Employee.objects.create(
            employee_number='E-EXT-EMP',
            first_name='Pat',
            last_name='Person',
        )
        self.contract = Contract.objects.create(
            employee=self.person,
            weekly_hours=Decimal('39.000'),
            job_number='C-EXT-100',
            valid_from=date(2025, 1, 1),
            is_active=True,
        )
        self.wbs = WBSElement.objects.create(wbs_code='EXT-1', title='Extension PSP')
        self.allocation = FundingAllocation.objects.create(
            contract=self.contract,
            employee=self.person,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('100.00'),
            job_number='J-EXT-200',
            start_date=date(2025, 1, 1),
            is_active=True,
        )
        self.task = PersonnelContractExtensionTask.objects.create(
            task_type='personnel_contract_extension',
            creator=self.creator,
            assignee=self.approver,
            employee=self.person,
            plan_position_number='P-1',
            valid_from=date(2026, 10, 1),
        )

    def test_assigned_approver_sees_current_contract_and_funding_job_numbers(self):
        self.client.login(username='ext-approver', password='test')
        response = self.client.get(reverse('tasks:task_detail', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current Job Numbers')
        self.assertContains(response, 'C-EXT-100')
        self.assertContains(response, 'J-EXT-200')
        self.assertContains(response, 'EXT-1')

    def test_creator_without_approval_rights_does_not_see_job_numbers(self):
        self.client.login(username='ext-creator', password='test')
        response = self.client.get(reverse('tasks:task_detail', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Current Job Numbers')
        self.assertNotContains(response, 'C-EXT-100')
        self.assertNotContains(response, 'J-EXT-200')
