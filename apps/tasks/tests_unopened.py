from datetime import date

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.template_variables import build_replacement_map
from apps.hr.models import Employee
from apps.tasks.models import PersonnelReallocationTask, PurchaseOrderTask, Task, TaskInitialOpen
from apps.tasks.unopened import tasks_menu_needs_attention, unopened_tasks_for_user


def _ready_user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


def _grant(user, model, *codenames):
    ct = ContentType.objects.get_for_model(model)
    for code in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=code))


class UnopenedTaskNotificationTests(TestCase):
    def setUp(self):
        self.creator_user = _ready_user('creator')
        self.creator = Employee.objects.create(
            employee_number='E-UNOP-C',
            first_name='Crea',
            last_name='Tor',
            user=self.creator_user,
        )
        self.coord_user = _ready_user('coord')
        _grant(self.coord_user, Task, 'view_all_personnel_tasks')
        self.coord = Employee.objects.create(
            employee_number='E-UNOP-K',
            first_name='Co',
            last_name='Ord',
            user=self.coord_user,
        )
        self.appr_user = _ready_user('approver')
        _grant(self.appr_user, Task, 'approve_personnel_task')
        self.approver = Employee.objects.create(
            employee_number='E-UNOP-A',
            first_name='App',
            last_name='Rover',
            user=self.appr_user,
        )
        self.person = Employee.objects.create(
            employee_number='E-UNOP-P',
            first_name='Pat',
            last_name='Person',
        )
        self.unassigned = PersonnelReallocationTask.objects.create(
            task_type='personnel_reallocation',
            creator=self.creator,
            employee=self.person,
            valid_from=date(2026, 9, 1),
        )
        self.assigned = PersonnelReallocationTask.objects.create(
            task_type='personnel_reallocation',
            creator=self.creator,
            assignee=self.approver,
            employee=self.person,
            valid_from=date(2026, 9, 2),
        )

    def test_coordinator_sees_unassigned_not_assigned(self):
        ids = set(unopened_tasks_for_user(self.coord_user).values_list('pk', flat=True))
        self.assertIn(self.unassigned.pk, ids)
        self.assertNotIn(self.assigned.pk, ids)
        self.assertTrue(tasks_menu_needs_attention(self.coord_user))

    def test_approver_sees_assigned_not_unassigned(self):
        ids = set(unopened_tasks_for_user(self.appr_user).values_list('pk', flat=True))
        self.assertIn(self.assigned.pk, ids)
        self.assertNotIn(self.unassigned.pk, ids)
        self.assertTrue(tasks_menu_needs_attention(self.appr_user))

    def test_completed_task_is_ignored(self):
        self.assigned.status = 'completed'
        self.assigned.save(update_fields=['status'])
        self.assertFalse(unopened_tasks_for_user(self.appr_user).exists())
        self.assertFalse(tasks_menu_needs_attention(self.appr_user))

    def test_opening_detail_clears_notification(self):
        client = Client()
        client.login(username='approver', password='test')
        response = client.get(reverse('tasks:task_detail', args=[self.assigned.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            TaskInitialOpen.objects.filter(user=self.appr_user, task=self.assigned).exists()
        )
        self.assertFalse(tasks_menu_needs_attention(self.appr_user))

    def test_plain_user_has_no_dot(self):
        self.assertFalse(tasks_menu_needs_attention(self.creator_user))

    def test_message_variable_lists_unopened_tasks(self):
        values = build_replacement_map(self.appr_user, self.approver)
        listing = values['unopened_tasks'].as_text()
        self.assertIn(self.assigned.task_number or f'#{self.assigned.pk}', listing)
        self.assertNotIn(self.unassigned.task_number or f'#{self.unassigned.pk}', listing)

    def test_procurement_coordinator_unassigned_po(self):
        po_user = _ready_user('proc-coord')
        _grant(po_user, PurchaseOrderTask, 'view_all_purchase_orders')
        Employee.objects.create(
            employee_number='E-UNOP-PC',
            first_name='Proc',
            last_name='Coord',
            user=po_user,
        )
        po = PurchaseOrderTask.objects.create(
            task_type='purchase_order',
            creator=self.creator,
            supplier='Acme',
        )
        ids = set(unopened_tasks_for_user(po_user).values_list('pk', flat=True))
        self.assertIn(po.pk, ids)
        self.assertNotIn(self.unassigned.pk, ids)
