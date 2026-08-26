"""Apply reallocation funding onto the employee record."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.finances.models import CostCenter, WBSElement
from apps.hr.models import Contract, Employee, FundingAllocation
from apps.tasks.models import (
    PersonnelReallocationTask,
    ReallocationFundingAllocation,
    Task,
)
from apps.tasks.reallocation_apply import (
    ApplyReallocationError,
    apply_reallocation_funding,
    build_apply_preview,
)


class ReallocationApplyTests(TestCase):
    def setUp(self):
        self.creator = Employee.objects.create(
            employee_number='E-APP-CRE',
            first_name='Creator',
            last_name='User',
        )
        self.person = Employee.objects.create(
            employee_number='E-APP-EMP',
            first_name='Reallocated',
            last_name='Person',
        )
        self.wbs_old = WBSElement.objects.create(wbs_code='OLD-1', title='Old PSP')
        self.wbs_new = WBSElement.objects.create(wbs_code='NEW-1', title='New PSP')
        self.cost_center = CostCenter.objects.create(cost_center='CC-APP')
        self.contract = Contract.objects.create(
            employee=self.person,
            weekly_hours=Decimal('39.00'),
            job_number='C-100',
            valid_from=date(2025, 1, 1),
            valid_until=None,
            is_active=True,
        )
        self.existing = FundingAllocation.objects.create(
            contract=self.contract,
            employee=self.person,
            wbs_element=self.wbs_old,
            workhours_percentage=Decimal('100.00'),
            plan_position_number='P-OLD',
            job_number='J-OLD',
            start_date=date(2025, 1, 1),
            end_date=date(2027, 12, 31),
            is_active=True,
        )
        self.task = PersonnelReallocationTask.objects.create(
            task_type='personnel_reallocation',
            creator=self.creator,
            employee=self.person,
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 12, 31),
        )
        self.row = ReallocationFundingAllocation.objects.create(
            reallocation_task=self.task,
            wbs_element=self.wbs_new,
            workhours_percentage=Decimal('100.00'),
            plan_position_number='P-NEW',
            job_number='',
        )

    def test_preview_lists_longer_running_existing_allocation(self):
        preview = build_apply_preview(self.task)
        self.assertTrue(preview['has_contract'])
        self.assertTrue(preview['can_resume'])
        self.assertEqual(len(preview['conflicts']), 1)
        self.assertEqual(preview['conflicts'][0]['id'], self.existing.pk)

    def test_end_choice_truncates_existing_and_creates_new(self):
        created = apply_reallocation_funding(
            self.task,
            job_numbers={str(self.row.pk): 'J-NEW'},
            continuation_choices={str(self.existing.pk): 'end'},
        )
        self.assertEqual(created, 1)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.end_date, date(2026, 6, 30))
        self.row.refresh_from_db()
        self.assertEqual(self.row.job_number, 'J-NEW')
        new_rows = FundingAllocation.objects.filter(
            employee=self.person,
            wbs_element=self.wbs_new,
        )
        self.assertEqual(new_rows.count(), 1)
        new_fa = new_rows.get()
        self.assertEqual(new_fa.contract_id, self.contract.pk)
        self.assertEqual(new_fa.start_date, date(2026, 7, 1))
        self.assertEqual(new_fa.end_date, date(2026, 12, 31))
        self.assertEqual(new_fa.job_number, 'J-NEW')
        self.assertEqual(
            FundingAllocation.objects.filter(employee=self.person, start_date=date(2027, 1, 1)).count(),
            0,
        )

    def test_resume_choice_splits_existing_allocation(self):
        apply_reallocation_funding(
            self.task,
            job_numbers={str(self.row.pk): 'J-NEW'},
            continuation_choices={str(self.existing.pk): 'resume'},
        )
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.end_date, date(2026, 6, 30))
        resumed = FundingAllocation.objects.get(
            employee=self.person,
            wbs_element=self.wbs_old,
            start_date=date(2027, 1, 1),
        )
        self.assertEqual(resumed.end_date, date(2027, 12, 31))
        self.assertEqual(resumed.workhours_percentage, Decimal('100.00'))
        self.assertEqual(resumed.job_number, 'J-OLD')

    def test_missing_job_number_is_rejected(self):
        with self.assertRaises(ApplyReallocationError):
            apply_reallocation_funding(
                self.task,
                job_numbers={},
                continuation_choices={str(self.existing.pk): 'end'},
            )

    def test_missing_continuation_choice_is_rejected(self):
        with self.assertRaises(ApplyReallocationError):
            apply_reallocation_funding(
                self.task,
                job_numbers={str(self.row.pk): 'J-NEW'},
                continuation_choices={},
            )

    def test_reallocation_past_contract_end_is_blocked(self):
        self.contract.valid_until = date(2026, 9, 30)
        self.contract.save()
        preview = build_apply_preview(self.task)
        self.assertTrue(preview['exceeds_contract'])
        self.assertIn('follow-on contract', preview['exceeds_contract_message'])
        with self.assertRaises(ApplyReallocationError) as ctx:
            apply_reallocation_funding(
                self.task,
                job_numbers={str(self.row.pk): 'J-NEW'},
                continuation_choices={str(self.existing.pk): 'end'},
            )
        self.assertIn('follow-on contract', str(ctx.exception))
        self.assertFalse(
            FundingAllocation.objects.filter(
                employee=self.person,
                wbs_element=self.wbs_new,
            ).exists()
        )

    def test_open_ended_reallocation_past_contract_end_is_blocked(self):
        self.contract.valid_until = date(2026, 12, 31)
        self.contract.save()
        self.task.valid_until = None
        self.task.save(update_fields=['valid_until'])
        with self.assertRaises(ApplyReallocationError):
            apply_reallocation_funding(
                self.task,
                job_numbers={str(self.row.pk): 'J-NEW'},
                continuation_choices={str(self.existing.pk): 'end'},
            )

    def test_no_open_contract_is_rejected(self):
        self.contract.valid_until = date(2026, 1, 1)
        self.contract.is_active = False
        self.contract.save()
        with self.assertRaises(ApplyReallocationError):
            apply_reallocation_funding(
                self.task,
                job_numbers={str(self.row.pk): 'J-NEW'},
                continuation_choices={str(self.existing.pk): 'end'},
            )

    def test_shorter_overlapping_allocation_is_ended_without_choice(self):
        short = FundingAllocation.objects.create(
            contract=self.contract,
            employee=self.person,
            cost_center=self.cost_center,
            workhours_percentage=Decimal('20.00'),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 9, 30),
            is_active=True,
        )
        apply_reallocation_funding(
            self.task,
            job_numbers={str(self.row.pk): 'J-NEW'},
            continuation_choices={str(self.existing.pk): 'end'},
        )
        short.refresh_from_db()
        self.assertEqual(short.end_date, date(2026, 6, 30))

    def test_second_apply_does_not_duplicate_matching_rows(self):
        apply_reallocation_funding(
            self.task,
            job_numbers={str(self.row.pk): 'J-NEW'},
            continuation_choices={str(self.existing.pk): 'end'},
        )
        created_again = apply_reallocation_funding(
            self.task,
            job_numbers={str(self.row.pk): 'J-NEW'},
            continuation_choices={},
        )
        self.assertEqual(created_again, 0)
        self.assertEqual(
            FundingAllocation.objects.filter(
                employee=self.person,
                wbs_element=self.wbs_new,
            ).count(),
            1,
        )


class ReallocationApplyViewTests(TestCase):
    def setUp(self):
        self.password = 'test-pass'
        self.user = CustomUser.objects.create_user('approver', password=self.password)
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        perm = Permission.objects.get(
            codename='approve_personnel_task',
            content_type=ContentType.objects.get_for_model(Task),
        )
        self.user.user_permissions.add(perm)
        self.approver = Employee.objects.create(
            employee_number='E-APP-APR',
            first_name='Ann',
            last_name='Approver',
            user=self.user,
        )
        self.person = Employee.objects.create(
            employee_number='E-APP-TGT',
            first_name='Target',
            last_name='Employee',
        )
        self.wbs = WBSElement.objects.create(wbs_code='APP-V', title='Apply PSP')
        self.contract = Contract.objects.create(
            employee=self.person,
            weekly_hours=Decimal('39.00'),
            valid_from=date(2025, 1, 1),
            is_active=True,
        )
        self.task = PersonnelReallocationTask.objects.create(
            task_type='personnel_reallocation',
            creator=self.approver,
            assignee=self.approver,
            employee=self.person,
            valid_from=date(2026, 3, 1),
            valid_until=date(2026, 8, 31),
        )
        self.row = ReallocationFundingAllocation.objects.create(
            reallocation_task=self.task,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('100.00'),
            job_number='J-1',
        )

    def test_approver_can_apply(self):
        self.client.login(username='approver', password=self.password)
        response = self.client.post(
            reverse('tasks:apply_reallocation_funding', args=[self.task.pk]),
            {'apply_job_number-' + str(self.row.pk): 'J-1'},
        )
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(
            FundingAllocation.objects.filter(
                employee=self.person,
                wbs_element=self.wbs,
                job_number='J-1',
            ).exists()
        )

    def test_non_approver_cannot_apply(self):
        other_user = CustomUser.objects.create_user('other', password=self.password)
        other_user.password_changed = True
        other_user.save(update_fields=['password_changed'])
        Employee.objects.create(
            employee_number='E-APP-OTH',
            first_name='Other',
            last_name='User',
            user=other_user,
        )
        self.client.login(username='other', password=self.password)
        response = self.client.post(
            reverse('tasks:apply_reallocation_funding', args=[self.task.pk]),
            {'apply_job_number-' + str(self.row.pk): 'J-1'},
        )
        self.assertIn(response.status_code, (302, 303))
        self.assertFalse(FundingAllocation.objects.filter(wbs_element=self.wbs).exists())
