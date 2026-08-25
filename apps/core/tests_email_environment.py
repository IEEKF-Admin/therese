from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups


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
        self.client.login(username='mail-admin', password='test')
        with override_settings(
            EMAIL_HOST='smtp.example.org',
            EMAIL_HOST_USER='noreply@example.org',
            EMAIL_HOST_PASSWORD='super-secret-password',
            DEFAULT_FROM_EMAIL='noreply@example.org',
        ):
            response = self.client.get(reverse('core_settings:messaging'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Messaging')
        self.assertContains(response, 'EMAIL_HOST')
        self.assertContains(response, '.env.example')
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

    def test_old_email_environment_url_redirects(self):
        self.client.login(username='mail-admin', password='test')
        response = self.client.get(reverse('core_settings:email_environment'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core_settings:messaging'))
