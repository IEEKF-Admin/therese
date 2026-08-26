from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.account_emails import (
    _pause_seconds,
    generate_random_password,
    reset_passwords_for_employees,
    send_account_email,
)
from apps.accounts.models import AccountEmailTemplate, CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.hr.models import Employee


class RandomPasswordTests(TestCase):
    def test_password_is_random_and_not_welcome(self):
        samples = {generate_random_password() for _ in range(8)}
        self.assertEqual(len(samples), 8)
        for value in samples:
            self.assertNotEqual(value, 'Welcome')
            self.assertGreaterEqual(len(value), 12)


class AccountEmailSendTests(TestCase):
    def setUp(self):
        get_or_create_default_groups()
        assign_permissions_to_groups()
        self.user = CustomUser.objects.create_user(
            'annam',
            password='old-pass',
            first_name='Anna',
            last_name='Muster',
            email='fallback@example.org',
        )
        self.employee = Employee.objects.create(
            employee_number='E-MAIL-1',
            first_name='Anna',
            last_name='Muster',
            prefix='Dr.',
            email_professional='anna@institute.org',
            user=self.user,
        )

    def test_new_employee_gets_random_password_and_welcome_email(self):
        mail.outbox.clear()
        employee = Employee.objects.create(
            employee_number='E-NEW-1',
            first_name='Ben',
            last_name='Neu',
            email_professional='ben@institute.org',
        )
        employee.refresh_from_db()
        self.assertIsNotNone(employee.user_id)
        self.assertFalse(employee.user.password_changed)
        self.assertFalse(employee.user.check_password('Welcome'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['ben@institute.org'])
        self.assertIn('THERESE account', mail.outbox[0].subject)
        self.assertIn('ben@institute.org', mail.outbox[0].to)
        self.assertIn(employee.user.username, mail.outbox[0].alternatives[0][0])

    def test_reset_email_uses_reset_template(self):
        send_account_email(
            AccountEmailTemplate.KIND_PASSWORD_RESET,
            self.user,
            self.employee,
            'TempPass12ab',
        )
        self.assertEqual(len(mail.outbox), 1)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn('TempPass12ab', html)
        self.assertIn('annam', html)
        self.assertIn('Dr.', html)

    @override_settings(ACCOUNT_EMAIL_PAUSE_MIN=4, ACCOUNT_EMAIL_PAUSE_MAX=11)
    def test_pause_stays_in_window(self):
        values = [_pause_seconds() for _ in range(30)]
        self.assertTrue(all(4 <= value <= 11 for value in values))

    @override_settings(ACCOUNT_EMAIL_PAUSE_MIN=0, ACCOUNT_EMAIL_PAUSE_MAX=0)
    def test_bulk_reset_sends_for_users_only(self):
        pending = Employee.objects.create(
            employee_number='E-PEND-1',
            first_name='No',
            last_name='Login',
            is_pending=True,
        )
        reset_count, skipped = reset_passwords_for_employees([self.employee, pending])
        self.assertEqual(reset_count, 1)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(self.user.check_password('old-pass'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.password_changed)


class PasswordResetViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user('sysadmin', password='test')
        self.admin.password_changed = True
        self.admin.save(update_fields=['password_changed'])
        self.admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        self.hr = CustomUser.objects.create_user('hrsuper', password='test')
        self.hr.password_changed = True
        self.hr.save(update_fields=['password_changed'])
        self.hr.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        self.target = CustomUser.objects.create_user('target', password='keep-me')
        self.employee = Employee.objects.create(
            employee_number='E-RST-1',
            first_name='Tim',
            last_name='Target',
            email_professional='tim@institute.org',
            user=self.target,
        )

    def test_systemadmin_can_reset_from_employee_form(self):
        self.admin.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        self.client.login(username='sysadmin', password='test')
        response = self.client.get(reverse('hr:employee_update', args=[self.employee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reset Password')
        mail.outbox.clear()
        response = self.client.post(reverse('hr:employee_reset_password', args=[self.employee.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.target.refresh_from_db()
        self.assertFalse(self.target.check_password('keep-me'))
        self.assertFalse(self.target.password_changed)

    def test_hr_superassistant_does_not_see_reset_button(self):
        self.client.login(username='hrsuper', password='test')
        response = self.client.get(reverse('hr:employee_update', args=[self.employee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Reset Password')
        response = self.client.post(reverse('hr:employee_reset_password', args=[self.employee.pk]))
        self.assertEqual(response.status_code, 403)

    def test_no_button_without_login_user(self):
        pending = Employee.objects.create(
            employee_number='E-RST-PEND',
            first_name='Pat',
            last_name='Pending',
            is_pending=True,
        )
        self.admin.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        self.client.login(username='sysadmin', password='test')
        response = self.client.get(reverse('hr:employee_update', args=[pending.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Reset Password')

    def test_systemadmin_can_edit_account_email_templates(self):
        self.client.login(username='sysadmin', password='test')
        response = self.client.get(reverse('core_settings:global_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Account emails')
        self.assertContains(response, '{{ username }}')
        response = self.client.post(
            reverse('core_settings:global_settings'),
            {
                'action': 'save_account_emails',
                'subject_user_created': 'Welcome {{ first_name }}',
                'body_user_created': '<p>User {{ username }} / {{ password }}</p>',
                'subject_password_reset': 'Reset {{ first_name }}',
                'body_password_reset': '<p>New {{ password }}</p>',
            },
        )
        self.assertEqual(response.status_code, 302)
        created = AccountEmailTemplate.objects.get(kind='user_created')
        self.assertEqual(created.subject, 'Welcome {{ first_name }}')
        self.assertIn('{{ username }}', created.body_html)

    @override_settings(ACCOUNT_EMAIL_PAUSE_MIN=0, ACCOUNT_EMAIL_PAUSE_MAX=0)
    def test_bulk_reset_from_employee_list(self):
        self.admin.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        self.client.login(username='sysadmin', password='test')
        response = self.client.post(
            reverse('hr:employee_list'),
            {'action': 'reset_passwords', 'selected_ids': [str(self.employee.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.target.refresh_from_db()
        self.assertFalse(self.target.check_password('keep-me'))

    def test_hr_cannot_save_account_email_templates(self):
        self.client.login(username='hrsuper', password='test')
        response = self.client.post(
            reverse('core_settings:global_settings'),
            {
                'action': 'save_account_emails',
                'subject_user_created': 'Nope',
                'body_user_created': '<p>Nope</p>',
                'subject_password_reset': 'Nope',
                'body_password_reset': '<p>Nope</p>',
            },
        )
        self.assertEqual(response.status_code, 403)
