from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.hr.models import Employee, Workgroup
from apps.tasks.models import GenericTextTask, PurchaseOrderTask, TaskWorkflowCoordinator
from apps.tasks.workflow_config import (
    creator_has_coordinator_fallback,
    has_workflow_coordinators,
    resolve_creator_workgroup,
    save_workflow_coordinators_from_post,
)
from apps.accounts.permissions import GroupNames


class TaskWorkflowConfigTests(TestCase):
    def setUp(self):
        self.workgroup = Workgroup.objects.create(
            short_name='AI-Lab',
            long_name='AI Research Lab',
            pi=self._employee('PI-1', 'Ada', 'Pi'),
        )
        self.creator = self._employee('E-1', 'Chris', 'Creator')
        self.creator.workgroups.add(self.workgroup)
        self.coordinator = self._employee('E-2', 'Casey', 'Coordinator')
        coord_group, _ = Group.objects.get_or_create(name=GroupNames.PROCUREMENT_COORDINATION_RIGHTS)
        self.coordinator.user.groups.add(coord_group)

        self.admin_user = CustomUser.objects.create_user('admin', password='test')
        self.admin_user.password_changed = True
        self.admin_user.save(update_fields=['password_changed'])
        admin_group, _ = Group.objects.get_or_create(name=GroupNames.ASSISTING_ADMINS)
        self.admin_user.groups.add(admin_group)

    def _employee(self, number, first, last):
        user = CustomUser.objects.create_user(number.lower(), password='test')
        user.password_changed = True
        user.save(update_fields=['password_changed'])
        return Employee.objects.create(
            employee_number=number,
            first_name=first,
            last_name=last,
            user=user,
        )

    def _purchase_task(self, *, with_workgroup=True):
        task = PurchaseOrderTask.objects.create(
            creator=self.creator,
            creator_workgroup=self.workgroup if with_workgroup else None,
            task_type='purchase_order',
            supplier='Supplier GmbH',
            status='not_yet_processed',
        )
        return task

    def test_resolve_creator_workgroup(self):
        self.assertEqual(resolve_creator_workgroup(self.creator), self.workgroup)

    def test_fallback_when_no_coordinators_configured(self):
        task = self._purchase_task()
        self.assertFalse(has_workflow_coordinators(self.workgroup, 'purchase_order'))
        self.assertTrue(creator_has_coordinator_fallback(self.creator.user, task))

    def test_no_fallback_when_coordinator_configured(self):
        TaskWorkflowCoordinator.objects.create(
            workgroup=self.workgroup,
            task_type='purchase_order',
            coordinator=self.coordinator,
        )
        task = self._purchase_task()
        self.assertTrue(has_workflow_coordinators(self.workgroup, 'purchase_order'))
        self.assertFalse(creator_has_coordinator_fallback(self.creator.user, task))

    def test_save_workflow_coordinators_from_post(self):
        save_workflow_coordinators_from_post(self.workgroup, {
            'coordinators_purchase_order': [str(self.coordinator.pk)],
            'coordinators_generic_text': [],
        })
        self.assertTrue(has_workflow_coordinators(self.workgroup, 'purchase_order'))
        self.assertFalse(has_workflow_coordinators(self.workgroup, 'generic_text'))

    def test_admin_list_requires_assisting_admin(self):
        response = self.client.get(reverse('tasks:workflow_config_manage'))
        self.assertEqual(response.status_code, 302)

        self.client.login(username='admin', password='test')
        response = self.client.get(reverse('tasks:workflow_config_manage'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Task Workflow Coordinators')

    def test_generic_creator_fallback_allows_status_update(self):
        recipient = self._employee('E-3', 'Robin', 'Recipient')
        from apps.tasks.models import TaskComment

        task = GenericTextTask.objects.create(
            creator=self.creator,
            creator_workgroup=self.workgroup,
            task_type='generic_text',
            title='Need supplies',
            status='seen',
            recipient=recipient,
        )
        self.client.login(username='e-1', password='test')
        response = self.client.post(reverse('tasks:task_detail', args=[task.pk]), {
            'status': 'in_progress',
            'new_message': 'Updated by creator fallback.',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'in_progress')
        self.assertTrue(
            TaskComment.objects.filter(
                task=task,
                entry_type=TaskComment.ENTRY_USER_MESSAGE,
                text='Updated by creator fallback.',
            ).exists()
        )