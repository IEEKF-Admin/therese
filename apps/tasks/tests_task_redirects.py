from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.hr.models import Employee
from apps.tasks.models import GenericTextTask, PurchaseOrderTask


class TaskSaveRedirectTests(TestCase):
    def setUp(self):
        self.creator = CustomUser.objects.create_user('creator', password='test')
        self.recipient_user = CustomUser.objects.create_user('recipient', password='test')
        CustomUser.objects.filter(pk__in=[self.creator.pk, self.recipient_user.pk]).update(
            password_changed=True,
        )
        self.creator_employee = Employee.objects.create(
            employee_number='E-CR-1',
            first_name='Creator',
            last_name='User',
            user=self.creator,
        )
        self.recipient_employee = Employee.objects.create(
            employee_number='E-RC-1',
            first_name='Recipient',
            last_name='User',
            user=self.recipient_user,
        )
        create_perm = Permission.objects.get(
            codename='create_purchase_order',
            content_type=ContentType.objects.get_for_model(PurchaseOrderTask),
        )
        self.creator.user_permissions.add(create_perm)

    def test_generic_task_update_redirects_to_my_tasks(self):
        task = GenericTextTask.objects.create(
            task_type='generic_text',
            title='Help needed',
            creator=self.creator_employee,
            recipient=self.recipient_employee,
            status='seen',
            comment='Initial',
        )
        self.client.force_login(self.recipient_user)
        response = self.client.post(
            reverse('tasks:task_detail', kwargs={'pk': task.pk}),
            {
                'title': 'Help needed',
                'recipient': self.recipient_employee.pk,
                'priority': 'medium',
                'status': 'in_progress',
                'comment': 'Updated description',
            },
        )
        self.assertRedirects(
            response,
            reverse('tasks:my_tasks'),
            status_code=303,
            fetch_redirect_response=False,
        )

    def test_generic_task_create_redirects_to_my_tasks(self):
        self.client.force_login(self.creator)
        response = self.client.post(
            reverse('tasks:task_create') + '?type=generic_text',
            {
                'task_type': 'generic_text',
                'title': 'New request',
                'recipient': self.recipient_employee.pk,
                'priority': 'medium',
                'status': 'seen',
                'comment': 'Please review this.',
                'confirm_info': 'on',
            },
        )
        self.assertRedirects(
            response,
            reverse('tasks:my_tasks'),
            status_code=303,
            fetch_redirect_response=False,
        )