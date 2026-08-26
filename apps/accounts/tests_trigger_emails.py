from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.login_popups import (
    evaluate_login_popups,
    send_login_trigger_emails,
)
from apps.accounts.models import CustomUser, LoginPopupConfig, TriggerEmailSend
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.accounts.template_variables import (
    build_replacement_map,
    catalog_for_trigger,
    render_placeholders,
)
from apps.accounts.scheduler import should_start_scheduler
from apps.accounts.trigger_emails import send_due_contract_emails, send_login_time_trigger_emails
from apps.hr.models import Contract, Employee
from apps.tasks.models import GenericTextTask, PersonnelReallocationTask, PurchaseOrderTask, TaskComment


class TemplateVariableTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            'vars',
            password='test',
            first_name='Ben',
            last_name='Beta',
            email='user@example.org',
        )
        self.employee = Employee.objects.create(
            employee_number='E-VARS',
            first_name='Ben',
            last_name='Beta',
            email_professional='work@example.org',
            user=self.user,
        )

    def test_person_and_contract_placeholders(self):
        end_date = date.today() + timedelta(days=40)
        contract = Contract.objects.create(
            employee=self.employee,
            pay_scale_group='E13',
            experience_level=3,
            weekly_hours=Decimal('39.00'),
            valid_from=date.today() - timedelta(days=365),
            valid_until=end_date,
        )
        replacements = build_replacement_map(self.user, self.employee, contract=contract)
        rendered = render_placeholders(
            'Hello {{ first_name }}, ends {{ contract_end }}',
            replacements,
        )
        self.assertIn('Hello Ben', rendered)
        self.assertIn(end_date.strftime('%d.%m.%Y'), rendered)

    def test_personnel_task_placeholders_and_catalog(self):
        task = PersonnelReallocationTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='personnel_reallocation',
            employee=self.employee,
            valid_from=date.today(),
            valid_until=date.today() + timedelta(days=30),
        )
        replacements = build_replacement_map(self.user, self.employee, task=task)
        rendered = render_placeholders(
            '{{ personnel_employee_name }} {{ personnel_employee_number }} {{ personnel_valid_from }}',
            replacements,
        )
        self.assertIn('Ben Beta', rendered)
        self.assertIn('E-VARS', rendered)
        keys = {item['key'] for item in catalog_for_trigger('personnel_task_created')}
        self.assertIn('personnel_employee_name', keys)
        self.assertIn('personnel_tasks', keys)
        self.assertIn('my_personnel_tasks', keys)
        po_keys = {item['key'] for item in catalog_for_trigger('purchase_order_created')}
        self.assertIn('supplier', po_keys)
        self.assertIn('purchase_orders', po_keys)

    def test_html_escaping(self):
        self.employee.first_name = '<script>x</script>'
        self.employee.save(update_fields=['first_name'])
        self.user.first_name = ''
        self.user.save(update_fields=['first_name'])
        replacements = build_replacement_map(self.user, self.employee)
        html = render_placeholders('<p>Hi {{ first_name }}</p>', replacements, html=True)
        self.assertIn('&lt;script&gt;x&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)

    def test_purchase_order_list_by_status_excludes_archived(self):
        open_po = PurchaseOrderTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='purchase_order',
            supplier='Open GmbH',
        )
        other_po = PurchaseOrderTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='purchase_order',
            supplier='Coordinating GmbH',
        )
        other_po.status = 'in_coordination'
        other_po.save()
        archived_po = PurchaseOrderTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='purchase_order',
            supplier='Archived GmbH',
        )
        archived_po.archived_by.add(self.employee)

        replacements = build_replacement_map(self.user, self.employee)
        text = render_placeholders(
            '{{ purchase_orders_not_yet_processed }}',
            replacements,
            html=False,
            user=self.user,
            employee=self.employee,
        )
        self.assertIn('Open GmbH', text)
        self.assertNotIn('Coordinating GmbH', text)
        self.assertNotIn('Archived GmbH', text)

        html = render_placeholders(
            '{{ purchase_orders:in_coordination }}',
            replacements,
            html=True,
            user=self.user,
            employee=self.employee,
        )
        self.assertIn('<table', html)
        self.assertIn('Coordinating GmbH', html)
        self.assertNotIn('Open GmbH', html)
        self.assertNotIn('&lt;table', html)

        mine = render_placeholders(
            '{{ my_purchase_orders }}',
            replacements,
            html=False,
            user=self.user,
            employee=self.employee,
        )
        self.assertIn('Open GmbH', mine)
        self.assertIn('Coordinating GmbH', mine)
        self.assertNotIn('Archived GmbH', mine)

        empty = render_placeholders(
            '{{ purchase_orders_delivered }}',
            replacements,
            html=False,
        )
        self.assertEqual(empty, 'None')


class TriggerEmailSendTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            'mailuser',
            password='test',
            first_name='Cara',
            last_name='Gamma',
            email='fallback@example.org',
        )
        self.employee = Employee.objects.create(
            employee_number='E-MAIL',
            first_name='Cara',
            last_name='Gamma',
            email_professional='cara@institute.org',
            user=self.user,
        )
        self.config = LoginPopupConfig.objects.create(
            name='Welcome mail',
            trigger='first_login',
            text='Popup hello {{ first_name }}',
            email_subject='Hi {{ first_name }}',
            email_html='<p>Welcome {{ first_name }} {{ last_name }}</p>',
            show_popup=True,
            send_email=True,
            enabled=True,
        )

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_first_login_email_sends_at_login(self):
        results = evaluate_login_popups(self.user, employee=self.employee)
        self.assertEqual(len(results), 1)
        send_login_time_trigger_emails(self.user, self.employee)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['cara@institute.org'])
        self.assertEqual(message.subject, 'Hi Cara')
        self.assertIn('Welcome Cara Gamma', message.alternatives[0][0])
        self.assertEqual(message.alternatives[0][1], 'text/html')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_falls_back_to_user_email(self):
        self.employee.email_professional = ''
        self.employee.save(update_fields=['email_professional'])
        send_login_time_trigger_emails(self.user, self.employee)
        self.assertEqual(mail.outbox[0].to, ['fallback@example.org'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_does_not_send_when_flag_off(self):
        self.config.send_email = False
        self.config.save(update_fields=['send_email'])
        send_login_time_trigger_emails(self.user, self.employee)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_email_only_first_login_does_not_show_popup(self):
        self.config.show_popup = False
        self.config.save(update_fields=['show_popup'])
        results = evaluate_login_popups(self.user, employee=self.employee)
        self.assertEqual(results, [])
        send_login_time_trigger_emails(self.user, self.employee)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_first_login_email_not_sent_twice(self):
        send_login_time_trigger_emails(self.user, self.employee)
        send_login_time_trigger_emails(self.user, self.employee)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(TriggerEmailSend.objects.count(), 1)

    def test_smtp_failure_does_not_raise(self):
        with patch(
            'apps.accounts.trigger_emails.send_therese_html_email',
            side_effect=OSError('smtp down'),
        ):
            send_login_time_trigger_emails(self.user, self.employee)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_task_assigned_sends_immediately_not_at_login(self):
        self.config.trigger = 'new_task_assigned'
        self.config.email_html = '<p>Task {{ task_title }} for {{ first_name }}</p>'
        self.config.email_subject = 'Task {{ task_title }}'
        self.config.save(update_fields=['trigger', 'email_html', 'email_subject'])
        task = GenericTextTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='generic_text',
            title='Lab coats',
            status='seen',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Task Lab coats', mail.outbox[0].subject)
        self.assertIn('Task Lab coats for Cara', mail.outbox[0].alternatives[0][0])

        self.user.last_login = timezone.now() - timedelta(days=1)
        self.user.save(update_fields=['last_login'])
        results = evaluate_login_popups(
            self.user,
            employee=self.employee,
            assigned_to_me=[task],
        )
        send_login_trigger_emails(self.user, results)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_task_assigned_does_not_resend_on_later_save(self):
        self.config.trigger = 'new_task_assigned'
        self.config.email_html = '<p>Assigned</p>'
        self.config.email_subject = 'Assigned'
        self.config.save(update_fields=['trigger', 'email_html', 'email_subject'])
        task = GenericTextTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='generic_text',
            title='Lab coats',
        )
        self.assertEqual(len(mail.outbox), 1)
        task.title = 'Lab coats updated'
        task.save()
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_status_change_emails_creator_immediately(self):
        self.config.trigger = 'task_status_changed'
        self.config.email_html = '<p>Status {{ task_status }}</p>'
        self.config.email_subject = 'Status {{ task_status }}'
        self.config.save(update_fields=['trigger', 'email_html', 'email_subject'])
        other = CustomUser.objects.create_user('assignee', password='test', email='a@example.org')
        other_emp = Employee.objects.create(
            employee_number='E-ASG',
            first_name='Ann',
            last_name='Assignee',
            email_professional='ann@institute.org',
            user=other,
        )
        task = GenericTextTask.objects.create(
            creator=self.employee,
            assignee=other_emp,
            task_type='generic_text',
            title='Need help',
        )
        self.assertEqual(len(mail.outbox), 0)
        task.status = 'completed'
        task.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['cara@institute.org'])
        self.assertIn('Status completed', mail.outbox[0].subject)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_purchase_order_created_notifies_audience(self):
        self.config.trigger = 'purchase_order_created'
        self.config.email_html = '<p>PO {{ supplier }} {{ task_number }}</p>'
        self.config.email_subject = 'New PO {{ supplier }}'
        self.config.save(update_fields=['trigger', 'email_html', 'email_subject'])
        PurchaseOrderTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='purchase_order',
            supplier='Acme GmbH',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('New PO Acme GmbH', mail.outbox[0].subject)
        GenericTextTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='generic_text',
            title='Ignore me',
        )
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_personnel_task_created_notifies_audience(self):
        self.config.trigger = 'personnel_task_created'
        self.config.email_html = '<p>{{ personnel_employee_name }} from {{ personnel_valid_from }}</p>'
        self.config.email_subject = 'Personnel {{ personnel_employee_name }}'
        self.config.save(update_fields=['trigger', 'email_html', 'email_subject'])
        PersonnelReallocationTask.objects.create(
            creator=self.employee,
            assignee=self.employee,
            task_type='personnel_reallocation',
            employee=self.employee,
            valid_from=date.today(),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Personnel Cara Gamma', mail.outbox[0].subject)
        self.assertIn('Cara Gamma from', mail.outbox[0].alternatives[0][0])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_comment_emails_creator_immediately(self):
        self.config.trigger = 'task_comment_on_created_task'
        self.config.email_html = '<p>{{ comment_author }}: {{ comment_text }}</p>'
        self.config.email_subject = 'Comment on {{ task_title }}'
        self.config.save(update_fields=['trigger', 'email_html', 'email_subject'])
        other = CustomUser.objects.create_user('writer', password='test', email='w@example.org')
        other_emp = Employee.objects.create(
            employee_number='E-WR',
            first_name='Will',
            last_name='Writer',
            user=other,
        )
        task = GenericTextTask.objects.create(
            creator=self.employee,
            assignee=other_emp,
            task_type='generic_text',
            title='Need help',
        )
        TaskComment.objects.create(
            task=task,
            author=other_emp,
            entry_type=TaskComment.ENTRY_USER_MESSAGE,
            text='Please check the quote.',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['cara@institute.org'])
        self.assertIn('Please check the quote.', mail.outbox[0].alternatives[0][0])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_contract_save_sends_when_in_window(self):
        self.config.trigger = 'contract_ending_soon'
        self.config.x_months = 6
        self.config.email_html = '<p>Ends {{ contract_end }}</p>'
        self.config.email_subject = 'Contract {{ contract_end }}'
        self.config.save(update_fields=['trigger', 'x_months', 'email_html', 'email_subject'])
        end_date = date.today() + timedelta(days=40)
        Contract.objects.create(
            employee=self.employee,
            pay_scale_group='E13',
            experience_level=3,
            weekly_hours=Decimal('39.00'),
            valid_from=date.today() - timedelta(days=365),
            valid_until=end_date,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(end_date.strftime('%d.%m.%Y'), mail.outbox[0].subject)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_due_command_sends_existing_window_contract(self):
        self.config.trigger = 'contract_ending_soon'
        self.config.x_months = 6
        self.config.send_email = False
        self.config.email_html = '<p>Ends {{ contract_end }}</p>'
        self.config.email_subject = 'Due {{ contract_end }}'
        self.config.save(update_fields=[
            'trigger', 'x_months', 'send_email', 'email_html', 'email_subject',
        ])
        end_date = date.today() + timedelta(days=40)
        Contract.objects.create(
            employee=self.employee,
            pay_scale_group='E13',
            experience_level=3,
            weekly_hours=Decimal('39.00'),
            valid_from=date.today() - timedelta(days=365),
            valid_until=end_date,
        )
        self.assertEqual(len(mail.outbox), 0)
        self.config.send_email = True
        self.config.save(update_fields=['send_email'])
        send_due_contract_emails()
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_login_sends_window_contract_without_daily_job(self):
        self.config.trigger = 'contract_ending_soon'
        self.config.x_months = 6
        self.config.send_email = False
        self.config.email_html = '<p>Ends {{ contract_end }}</p>'
        self.config.email_subject = 'Login {{ contract_end }}'
        self.config.save(update_fields=[
            'trigger', 'x_months', 'send_email', 'email_html', 'email_subject',
        ])
        end_date = date.today() + timedelta(days=40)
        Contract.objects.create(
            employee=self.employee,
            pay_scale_group='E13',
            experience_level=3,
            weekly_hours=Decimal('39.00'),
            valid_from=date.today() - timedelta(days=365),
            valid_until=end_date,
        )
        self.assertEqual(len(mail.outbox), 0)
        self.config.send_email = True
        self.config.save(update_fields=['send_email'])
        send_login_time_trigger_emails(self.user, self.employee)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(end_date.strftime('%d.%m.%Y'), mail.outbox[0].subject)


class ContractEmailSchedulerTests(TestCase):
    def test_scheduler_does_not_start_during_tests(self):
        self.assertFalse(should_start_scheduler(['manage.py', 'test']))

    def test_scheduler_starts_for_runserver_child(self):
        self.assertFalse(should_start_scheduler(['manage.py', 'runserver']))
        with patch.dict('os.environ', {'RUN_MAIN': 'true'}):
            self.assertTrue(should_start_scheduler(['manage.py', 'runserver']))

    def test_scheduler_can_be_disabled(self):
        with patch.dict('os.environ', {'THERESE_DISABLE_SCHEDULER': '1', 'RUN_MAIN': 'true'}):
            self.assertFalse(should_start_scheduler(['manage.py', 'runserver']))


class EmailTemplateSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.allowed = CustomUser.objects.create_user('mail-admin', password='test')
        self.allowed.password_changed = True
        self.allowed.save(update_fields=['password_changed'])
        self.allowed.groups.add(Group.objects.get(name=GroupNames.EMAIL_CONFIGURE))
        self.config = LoginPopupConfig.objects.create(
            name='Contract mail',
            trigger='contract_ending_soon',
            text='Popup',
            x_months=6,
            enabled=True,
        )

    def test_page_lists_trigger_templates(self):
        self.client.login(username='mail-admin', password='test')
        response = self.client.get(reverse('core_settings:messaging'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Messaging')
        self.assertContains(response, 'Contract mail')
        self.assertContains(response, 'New task assigned to the user')
        self.assertContains(response, 'New purchase order (procurement) created')
        self.assertContains(response, 'New personnel task created')
        self.assertContains(response, 'First login (welcome / profile completion)')
        self.assertContains(response, 'Email body')
        self.assertContains(response, '{{ first_name }}')

    def test_group_can_create_template_for_trigger(self):
        self.client.login(username='mail-admin', password='test')
        response = self.client.post(
            reverse('core_settings:messaging'),
            {
                'action': 'save_config',
                'trigger': 'new_task_assigned',
                'name': 'Assigned task mail',
                'send_email': 'on',
                'email_subject': 'New task {{ task_title }}',
                'email_html': '<p>Assigned {{ task_title }}</p>',
            },
        )
        self.assertEqual(response.status_code, 302)
        created = LoginPopupConfig.objects.get(name='Assigned task mail')
        self.assertEqual(created.trigger, 'new_task_assigned')
        self.assertTrue(created.send_email)
        self.assertFalse(created.show_popup)
        self.assertEqual(created.email_subject, 'New task {{ task_title }}')
        self.assertIn('Assigned {{ task_title }}', created.email_html)

    def test_login_popup_settings_shows_reaction_checkboxes(self):
        assistant = CustomUser.objects.create_user('hr-super', password='test')
        assistant.password_changed = True
        assistant.save(update_fields=['password_changed'])
        assistant.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        client = Client()
        client.login(username='hr-super', password='test')
        response = client.get(reverse('accounts:login_popup_settings'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Messaging')
        self.assertContains(response, 'Show popup')
        self.assertContains(response, 'Send email')
        self.assertContains(response, 'Popup text')

    def test_group_can_save_template(self):
        self.client.login(username='mail-admin', password='test')
        response = self.client.post(
            reverse('core_settings:messaging'),
            {
                'action': 'save_config',
                'pk': str(self.config.pk),
                'name': self.config.name,
                'trigger': self.config.trigger,
                'send_email': 'on',
                'email_subject': 'Hello {{ first_name }}',
                'email_html': '<p>Hi {{ first_name }}</p><script>alert(1)</script>',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertTrue(self.config.send_email)
        self.assertEqual(self.config.email_subject, 'Hello {{ first_name }}')
        self.assertIn('<p>Hi {{ first_name }}</p>', self.config.email_html)
        self.assertNotIn('<script>', self.config.email_html)
