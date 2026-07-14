from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.hr.models import Employee
from apps.tasks.forms import PurchaseOrderQuoteReplaceForm, PurchaseOrderTaskForm
from apps.tasks.models import PurchaseOrderTask, TaskComment


class PurchaseOrderQuoteFormTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('buyer', password='test')
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        create_perm = Permission.objects.get(
            codename='create_purchase_order',
            content_type=ContentType.objects.get_for_model(PurchaseOrderTask),
        )
        self.user.user_permissions.add(create_perm)
        self.employee = Employee.objects.create(
            employee_number='E-QUOTE-1',
            first_name='Buyer',
            last_name='User',
            user=self.user,
        )
        self.pdf = SimpleUploadedFile('quote.pdf', b'%PDF-1.4 quote', content_type='application/pdf')

    def test_quote_order_creation_requires_pdf(self):
        form = PurchaseOrderTaskForm(
            data={'status': 'not_yet_processed'},
            files={},
            user=self.user,
            is_creation=True,
            quote_order_mode=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('quote_file', form.errors)

    def test_quote_order_creation_accepts_pdf_only(self):
        form = PurchaseOrderTaskForm(
            data={'status': 'not_yet_processed'},
            files={'quote_file': self.pdf},
            user=self.user,
            is_creation=True,
            quote_order_mode=True,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_regular_purchase_order_accepts_optional_quote(self):
        form = PurchaseOrderTaskForm(
            data={
                'supplier': 'Supplier GmbH',
                'priority': 'medium',
                'status': 'not_yet_processed',

            },
            files={'quote_file': self.pdf},
            user=self.user,
            is_creation=True,
            quote_order_mode=False,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_quote_order_marks_instance_on_save(self):
        form = PurchaseOrderTaskForm(
            data={'status': 'not_yet_processed'},
            files={'quote_file': self.pdf},
            user=self.user,
            is_creation=True,
            quote_order_mode=True,
        )
        self.assertTrue(form.is_valid(), form.errors)
        task = form.save(commit=False)
        task.creator = self.employee
        task.task_type = 'purchase_order'
        task.save()
        self.assertTrue(task.is_quote_order)
        self.assertEqual(task.supplier, '')
        self.assertTrue(task.quote_file.name.endswith('.pdf'))


class PurchaseOrderQuoteViewTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('buyer', password='test')
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        create_perm = Permission.objects.get(
            codename='create_purchase_order',
            content_type=ContentType.objects.get_for_model(PurchaseOrderTask),
        )
        self.user.user_permissions.add(create_perm)
        self.employee = Employee.objects.create(
            employee_number='E-QUOTE-2',
            first_name='Buyer',
            last_name='User',
            user=self.user,
        )
        self.other = CustomUser.objects.create_user('other', password='test')
        self.other.password_changed = True
        self.other.save(update_fields=['password_changed'])
        Employee.objects.create(
            employee_number='E-QUOTE-3',
            first_name='Other',
            last_name='User',
            user=self.other,
        )
        self.task = PurchaseOrderTask.objects.create(
            creator=self.employee,
            task_type='purchase_order',
            is_quote_order=True,
            supplier='',
            status='not_yet_processed',
            quote_file=SimpleUploadedFile('quote.pdf', b'%PDF-1.4 quote', content_type='application/pdf'),
        )

    def test_creator_can_replace_quote(self):
        self.client.force_login(self.user)
        replacement = SimpleUploadedFile('new-quote.pdf', b'%PDF-1.4 new', content_type='application/pdf')
        response = self.client.post(
            reverse('tasks:purchase_order_quote_replace', args=[self.task.pk]),
            {'quote_file': replacement},
        )
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertTrue(self.task.quote_file.name.endswith('.pdf'))
        self.assertTrue(
            TaskComment.objects.filter(
                task=self.task,
                entry_type=TaskComment.ENTRY_EDITED,
            ).exists()
        )

    def test_non_creator_cannot_replace_quote(self):
        self.client.force_login(self.other)
        replacement = SimpleUploadedFile('new-quote.pdf', b'%PDF-1.4 new', content_type='application/pdf')
        response = self.client.post(
            reverse('tasks:purchase_order_quote_replace', args=[self.task.pk]),
            {'quote_file': replacement},
        )
        self.assertIn(response.status_code, (302, 303))
        self.assertEqual(response['Location'], reverse('tasks:my_tasks'))

    def test_creator_can_download_quote(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('tasks:purchase_order_quote_download', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_replace_form_rejects_non_pdf(self):
        form = PurchaseOrderQuoteReplaceForm(
            files={'quote_file': SimpleUploadedFile('quote.txt', b'plain text', content_type='text/plain')},
            instance=self.task,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('quote_file', form.errors)