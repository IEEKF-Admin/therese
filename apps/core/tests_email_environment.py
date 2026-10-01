from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.core.mail import mail_params, smtp_security
from apps.core.models import GlobalSetting


def _ready_user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class EmailEnvironmentPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.allowed = _ready_user('mail-admin')
        self.allowed.groups.add(Group.objects.get(name=GroupNames.EMAIL_CONFIGURE))
        self.denied = _ready_user('mail-denied')

    def test_group_can_open_page_and_password_is_hidden(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'smtp_host': 'smtp.example.org',
                'smtp_user': 'noreply@example.org',
                'smtp_password': 'super-secret-password',
                'smtp_from_email': 'noreply@example.org',
            },
        )
        self.client.login(username='mail-admin', password='test')
        response = self.client.get(reverse('core_settings:messaging'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Messaging')
        self.assertContains(response, 'Global Settings → SMTP')
        self.assertContains(response, 'Configured (value hidden)')
        self.assertNotContains(response, 'super-secret-password')
        self.assertContains(response, 'New task assigned to the user')
        self.assertContains(response, 'Own contract ending in X months')
        self.assertContains(response, 'Email body')

    def test_other_users_are_forbidden(self):
        self.client.login(username='mail-denied', password='test')
        response = self.client.get(reverse('core_settings:messaging'))
        self.assertEqual(response.status_code, 403)

    def test_group_can_send_test_email(self):
        self.client.login(username='mail-admin', password='test')
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            response = self.client.post(
                reverse('core_settings:messaging'),
                {'action': 'send_test', 'recipient': 'tester@example.org'},
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['tester@example.org'])
        self.assertIn('THERESE email test', mail.outbox[0].subject)

    def test_denied_user_cannot_send_test_email(self):
        self.client.login(username='mail-denied', password='test')
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            response = self.client.post(
                reverse('core_settings:messaging'),
                {'action': 'send_test', 'recipient': 'tester@example.org'},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_status_uses_global_settings(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'smtp_host': 'smtp.db.example',
                'smtp_port': 587,
                'smtp_use_ssl': False,
                'smtp_use_tls': True,
                'smtp_user': 'db@example.org',
                'smtp_password': 'db-secret',
                'smtp_from_email': 'from-db@example.org',
            },
        )
        self.client.login(username='mail-admin', password='test')
        response = self.client.get(reverse('core_settings:messaging'))
        self.assertContains(response, 'smtp.db.example')
        self.assertContains(response, 'from-db@example.org')
        self.assertContains(response, 'Global Settings → SMTP')
        self.assertNotContains(response, 'db-secret')

    def test_old_email_environment_url_redirects(self):
        self.client.login(username='mail-admin', password='test')
        response = self.client.get(reverse('core_settings:email_environment'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core_settings:messaging'))


class MailParamsTests(TestCase):
    def test_env_host_does_not_override_db(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'smtp_host': 'smtp.db.example',
                'smtp_from_email': 'from-db@example.org',
                'smtp_password': 'db-secret',
            },
        )
        with override_settings(
            EMAIL_HOST='smtp.env.example',
            EMAIL_PORT=465,
            EMAIL_HOST_USER='env@example.org',
            EMAIL_HOST_PASSWORD='env-secret',
            EMAIL_USE_SSL=True,
            EMAIL_USE_TLS=False,
            DEFAULT_FROM_EMAIL='from-env@example.org',
        ):
            params = mail_params()
        self.assertEqual(params['source'], 'db')
        self.assertEqual(params['host'], 'smtp.db.example')
        self.assertEqual(params['from_email'], 'from-db@example.org')
        self.assertEqual(params['password'], 'db-secret')

    def test_db_used(self):
        setting = GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'smtp_host': 'smtp.db.example',
                'smtp_port': 587,
                'smtp_use_ssl': False,
                'smtp_use_tls': True,
                'smtp_user': 'db@example.org',
                'smtp_from_email': 'from-db@example.org',
                'smtp_password': 'db-secret',
            },
        )[0]
        params = mail_params(setting)
        self.assertEqual(params['source'], 'db')
        self.assertEqual(params['host'], 'smtp.db.example')
        self.assertEqual(params['port'], 587)
        self.assertEqual(params['from_email'], 'from-db@example.org')
        self.assertTrue(params['use_tls'])
        self.assertFalse(params['use_ssl'])

    def test_port_587_with_ssl_flag_uses_starttls(self):
        setting = GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'smtp_host': 'smtp.db.example',
                'smtp_port': 587,
                'smtp_use_ssl': True,
                'smtp_use_tls': False,
                'smtp_from_email': 'from-db@example.org',
            },
        )[0]
        params = mail_params(setting)
        self.assertFalse(params['use_ssl'])
        self.assertTrue(params['use_tls'])
        self.assertEqual(smtp_security(465, False, True), (True, False))
        self.assertEqual(smtp_security(25, True, False), (False, True))
