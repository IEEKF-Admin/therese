"""Google Calendar sharing and the Systemadmin accounts tab."""

import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.core.models import GlobalSetting
from apps.hr.models import Contract, Employee, EmployeeExternalAccount, Workgroup
from apps.hr.provisioning import sync_employee_google_calendar


class FakeCalendar:
    def __init__(self):
        self.shared = set()
        self.calls = []

    def share(self, email, role='writer'):
        email = email.lower()
        self.calls.append(('share', email, role))
        self.shared.add(email)

    def unshare(self, email):
        email = email.lower()
        self.calls.append(('unshare', email))
        self.shared.discard(email)

    def list_shared_emails(self):
        return sorted(self.shared)


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


SA_EMAIL = 'therese@example.iam.gserviceaccount.com'
SA_JSON = json.dumps({
    'type': 'service_account',
    'client_email': SA_EMAIL,
    'private_key': (
        '-----BEGIN PRIVATE KEY-----\n'
        'not-a-real-key\n'
        '-----END PRIVATE KEY-----\n'
    ),
})


@override_settings(GOOGLE_SERVICE_ACCOUNT_JSON='', GOOGLE_SERVICE_ACCOUNT_FILE='')
class GoogleCalendarProvisioningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.fake = FakeCalendar()
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_calendar_enabled': True,
                'google_calendar_id': 'cal-1',
                'google_service_account_json': SA_JSON,
                'google_service_account_email': SA_EMAIL,
            },
        )
        self.employee = Employee.objects.create(
            employee_number='GC1',
            first_name='Ada',
            last_name='Lovelace',
            google_account='ada@gmail.com',
        )
        Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('39.000'),
            valid_from=date.today() - timedelta(days=10),
            valid_until=None,
            is_active=True,
        )

    def test_disabled_does_not_call_google(self):
        GlobalSetting.objects.filter(pk=1).update(google_calendar_enabled=False)
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            result = sync_employee_google_calendar(self.employee)
        self.assertEqual(result, 'skipped')
        self.assertEqual(self.fake.calls, [])

    def test_share_when_google_account_set(self):
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            result = sync_employee_google_calendar(self.employee)
        self.assertEqual(result, 'active')
        self.assertIn('ada@gmail.com', self.fake.shared)
        row = EmployeeExternalAccount.objects.get(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
        )
        self.assertEqual(row.status, EmployeeExternalAccount.Status.ACTIVE)
        self.assertEqual(row.identifier, 'ada@gmail.com')

    def test_replace_acl_when_google_account_changes(self):
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            sync_employee_google_calendar(self.employee)
            self.employee.google_account = 'ada.new@gmail.com'
            self.employee.save()
            with self.captureOnCommitCallbacks(execute=True):
                sync_employee_google_calendar(self.employee)
        self.assertNotIn('ada@gmail.com', self.fake.shared)
        self.assertIn('ada.new@gmail.com', self.fake.shared)

    def test_unshare_when_archived(self):
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            sync_employee_google_calendar(self.employee)
            contract = self.employee.contracts.get()
            contract.valid_until = date.today() - timedelta(days=1)
            contract.save()
            result = sync_employee_google_calendar(self.employee)
        self.assertEqual(result, 'removed')
        self.assertNotIn('ada@gmail.com', self.fake.shared)
        row = EmployeeExternalAccount.objects.get(employee=self.employee)
        self.assertEqual(row.status, EmployeeExternalAccount.Status.REMOVED)
        self.assertEqual(row.identifier, 'ada@gmail.com')

    def test_removed_updates_identifier_when_google_account_changes(self):
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            sync_employee_google_calendar(self.employee)
            contract = self.employee.contracts.get()
            contract.valid_until = date.today() - timedelta(days=1)
            contract.save()
            sync_employee_google_calendar(self.employee)
            self.employee.google_account = 'ada.new@gmail.com'
            self.employee.save()
            result = sync_employee_google_calendar(self.employee)
        self.assertEqual(result, 'removed')
        row = EmployeeExternalAccount.objects.get(employee=self.employee)
        self.assertEqual(row.status, EmployeeExternalAccount.Status.REMOVED)
        self.assertEqual(row.identifier, 'ada.new@gmail.com')

    def test_reshare_on_restore(self):
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            sync_employee_google_calendar(self.employee)
            contract = self.employee.contracts.get()
            contract.valid_until = date.today() - timedelta(days=1)
            contract.save()
            sync_employee_google_calendar(self.employee)
            from apps.hr.employee_list_helpers import restore_employee_from_archive

            with self.captureOnCommitCallbacks(execute=True):
                ok, reason = restore_employee_from_archive(self.employee)
            self.assertTrue(ok, reason)
        self.assertIn('ada@gmail.com', self.fake.shared)

    def test_no_google_account_does_not_create_row(self):
        empty = Employee.objects.create(
            employee_number='GC0',
            first_name='No',
            last_name='Mail',
        )
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            result = sync_employee_google_calendar(empty)
        self.assertEqual(result, 'skipped')
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(
            EmployeeExternalAccount.objects.filter(employee=empty).exists()
        )

    def test_not_connected_marks_error_only_when_relevant(self):
        GlobalSetting.objects.filter(pk=1).update(
            google_service_account_json='',
            google_service_account_email='',
        )
        empty = Employee.objects.create(
            employee_number='GC0b',
            first_name='No',
            last_name='Token',
        )
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            self.assertEqual(sync_employee_google_calendar(empty), 'skipped')
            self.assertEqual(sync_employee_google_calendar(self.employee), 'error')
        self.assertFalse(
            EmployeeExternalAccount.objects.filter(employee=empty).exists()
        )
        row = EmployeeExternalAccount.objects.get(employee=self.employee)
        self.assertEqual(row.status, EmployeeExternalAccount.Status.ERROR)

    def test_save_schedules_sync(self):
        with patch('apps.hr.provisioning.get_calendar_client', return_value=self.fake):
            emp = Employee(
                employee_number='GC2',
                first_name='Alan',
                last_name='Turing',
                google_account='alan@gmail.com',
            )
            with self.captureOnCommitCallbacks(execute=True):
                emp.save()
                Contract.objects.create(
                    employee=emp,
                    weekly_hours=Decimal('20.000'),
                    valid_from=date.today(),
                    is_active=True,
                )
        self.assertIn('alan@gmail.com', self.fake.shared)


class GoogleCalendarAccountsTabTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.admin = _ready('sysadmin-gc')
        self.admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        emp_ct = ContentType.objects.get_for_model(Employee)
        wg_ct = ContentType.objects.get_for_model(Workgroup)
        self.admin.user_permissions.add(
            Permission.objects.get(content_type=emp_ct, codename='can_view_all_employees'),
            Permission.objects.get(content_type=emp_ct, codename='can_view_employees'),
            Permission.objects.get(content_type=wg_ct, codename='manage_working_group'),
        )
        self.hr = _ready('hr-gc')
        self.hr.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        self.employee = Employee.objects.create(
            employee_number='GC3',
            first_name='Grace',
            last_name='Hopper',
            google_account='grace@gmail.com',
        )
        EmployeeExternalAccount.objects.create(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
            identifier='grace@gmail.com',
            status=EmployeeExternalAccount.Status.ACTIVE,
        )

    def test_systemadmin_sees_accounts_tab_and_table(self):
        self.client.login(username='sysadmin-gc', password='test')
        listed = self.client.get(reverse('hr:employee_list'))
        self.assertEqual(listed.status_code, 200)
        self.assertContains(listed, 'Accounts')
        response = self.client.get(reverse('hr:employee_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Google Calendar')
        self.assertContains(response, 'Hopper')
        self.assertContains(response, 'aria-label="Shared"')
        self.assertContains(response, 'name="selected_ids"')
        self.assertContains(response, 'accounts-actions-toggle')
        self.assertContains(response, 'Add to Google Calendar')
        self.assertContains(response, 'Website')
        self.assertContains(response, 'accounts-row-archived')
        self.assertNotContains(response, 'badge-archived')
        self.assertNotContains(response, 'Employee No.')
        self.assertNotContains(response, 'grace@gmail.com')
        self.assertNotContains(response, 'Shared</span>')

    def test_accounts_table_hides_google_account_email(self):
        self.employee.google_account = 'grace.new@gmail.com'
        self.employee.save(update_fields=['google_account'])
        self.client.login(username='sysadmin-gc', password='test')
        response = self.client.get(reverse('hr:employee_accounts'))
        self.assertNotContains(response, 'grace.new@gmail.com')
        self.assertNotContains(response, 'grace@gmail.com')
        self.assertContains(response, 'aria-label="Shared"')

    def test_accounts_search_filters_like_employee_list(self):
        Employee.objects.create(
            employee_number='GC9',
            first_name='Ada',
            last_name='Lovelace',
            google_account='ada@gmail.com',
        )
        self.client.login(username='sysadmin-gc', password='test')
        response = self.client.get(reverse('hr:employee_accounts'), {'q': 'Hopper'})
        self.assertContains(response, 'Hopper')
        self.assertNotContains(response, 'Lovelace')
        self.assertContains(response, 'accounts-search')
        partial = self.client.get(
            reverse('hr:employee_accounts'),
            {'q': 'Ada', 'partial': '1'},
        )
        self.assertEqual(partial.status_code, 200)
        self.assertContains(partial, 'Lovelace')
        self.assertNotContains(partial, 'Hopper')
        self.assertNotIn('<html', partial.content.decode().lower())

    def test_bulk_calendar_remove_and_add(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_calendar_enabled': True,
                'google_calendar_id': 'cal-1',
                'google_service_account_json': SA_JSON,
                'google_service_account_email': SA_EMAIL,
            },
        )
        fake = FakeCalendar()
        fake.shared.add('grace@gmail.com')
        self.client.login(username='sysadmin-gc', password='test')
        with patch('apps.hr.provisioning.get_calendar_client', return_value=fake):
            removed = self.client.post(reverse('hr:employee_accounts_bulk'), {
                'action': 'calendar_remove',
                'selected_ids': [str(self.employee.pk)],
            })
        self.assertEqual(removed.status_code, 302)
        self.assertNotIn('grace@gmail.com', fake.shared)
        row = EmployeeExternalAccount.objects.get(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
        )
        self.assertEqual(row.status, EmployeeExternalAccount.Status.REMOVED)
        with patch('apps.hr.provisioning.get_calendar_client', return_value=fake):
            added = self.client.post(reverse('hr:employee_accounts_bulk'), {
                'action': 'calendar_add',
                'selected_ids': [str(self.employee.pk)],
            })
        self.assertEqual(added.status_code, 302)
        self.assertIn('grace@gmail.com', fake.shared)
        row.refresh_from_db()
        self.assertEqual(row.status, EmployeeExternalAccount.Status.ACTIVE)

    def test_hr_cannot_open_accounts_tab(self):
        self.client.login(username='hr-gc', password='test')
        listed = self.client.get(reverse('hr:employee_list'))
        self.assertEqual(listed.status_code, 200)
        self.assertNotContains(listed, reverse('hr:employee_accounts'))
        response = self.client.get(reverse('hr:employee_accounts'))
        self.assertEqual(response.status_code, 403)

    @override_settings(GOOGLE_SERVICE_ACCOUNT_JSON='', GOOGLE_SERVICE_ACCOUNT_FILE='')
    def test_integrations_shows_service_account_ui(self):
        self.client.login(username='sysadmin-gc', password='test')
        listed = self.client.get(reverse('core_settings:global_settings') + '?tab=integrations')
        self.assertContains(listed, 'Google service account JSON key')
        self.assertContains(listed, 'Test calendar connection')
        self.assertContains(listed, 'Make changes and manage sharing')
        self.assertNotContains(listed, 'Connect Google')
        self.assertNotContains(listed, 'Google OAuth client ID')

    @override_settings(GOOGLE_SERVICE_ACCOUNT_JSON='', GOOGLE_SERVICE_ACCOUNT_FILE='')
    def test_integrations_shows_saved_service_account(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_service_account_json': SA_JSON,
                'google_service_account_email': SA_EMAIL,
            },
        )
        self.client.login(username='sysadmin-gc', password='test')
        listed = self.client.get(reverse('core_settings:global_settings') + '?tab=integrations')
        self.assertContains(listed, SA_EMAIL)
        self.assertContains(listed, 'Sync calendar access now')


@override_settings(GOOGLE_SERVICE_ACCOUNT_JSON='', GOOGLE_SERVICE_ACCOUNT_FILE='')
class GoogleCalendarConnectionTestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.admin = _ready('sysadmin-gc-test')
        self.admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        self.hr = _ready('hr-gc-test')
        self.hr.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_calendar_enabled': False,
                'google_calendar_id': 'cal-1',
                'google_service_account_json': SA_JSON,
                'google_service_account_email': SA_EMAIL,
            },
        )

    def test_settings_page_has_test_button(self):
        self.client.login(username='sysadmin-gc-test', password='test')
        response = self.client.get(reverse('core_settings:global_settings') + '?tab=integrations')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test calendar connection')
        self.assertContains(response, reverse('core_settings:google_calendar_test'))

    def test_connection_ok(self):
        self.client.login(username='sysadmin-gc-test', password='test')
        with patch(
            'apps.core.google_oauth_views.probe_calendar_connection',
            return_value={'id': 'cal-1', 'summary': 'Institute'},
        ):
            response = self.client.post(
                reverse('core_settings:google_calendar_test'),
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'Calendar connection OK: Institute (as {SA_EMAIL}).',
        )

    def test_connection_requires_calendar_id(self):
        GlobalSetting.objects.filter(pk=1).update(google_calendar_id='')
        self.client.login(username='sysadmin-gc-test', password='test')
        response = self.client.post(
            reverse('core_settings:google_calendar_test'),
            follow=True,
        )
        self.assertContains(response, 'Set a Google Calendar ID first.')

    @override_settings(GOOGLE_SERVICE_ACCOUNT_JSON='', GOOGLE_SERVICE_ACCOUNT_FILE='')
    def test_connection_requires_service_account(self):
        GlobalSetting.objects.filter(pk=1).update(
            google_service_account_json='',
            google_service_account_email='',
        )
        self.client.login(username='sysadmin-gc-test', password='test')
        response = self.client.post(
            reverse('core_settings:google_calendar_test'),
            follow=True,
        )
        self.assertContains(response, 'Save a Google service account JSON key first.')

    def test_connection_reports_api_error(self):
        from apps.core.google_calendar import GoogleCalendarError

        self.client.login(username='sysadmin-gc-test', password='test')
        with patch(
            'apps.core.google_oauth_views.probe_calendar_connection',
            side_effect=GoogleCalendarError('Google API 404: not found'),
        ):
            response = self.client.post(
                reverse('core_settings:google_calendar_test'),
                follow=True,
            )
        self.assertContains(response, 'Calendar connection failed: Google API 404: not found')

    def test_hr_cannot_test_connection(self):
        self.client.login(username='hr-gc-test', password='test')
        response = self.client.post(reverse('core_settings:google_calendar_test'))
        self.assertEqual(response.status_code, 403)

    def test_probe_reports_missing_acl_permission(self):
        from apps.core.google_calendar import GoogleCalendarError, probe_calendar_connection

        with patch(
            'apps.core.google_calendar.service_account_access_token',
            return_value='access',
        ):
            with patch(
                'apps.core.google_calendar._http_json',
                side_effect=[
                    {'id': 'cal-1', 'summary': 'Institute'},
                    GoogleCalendarError('forbidden', status=403),
                ],
            ):
                with self.assertRaises(GoogleCalendarError) as ctx:
                    probe_calendar_connection()
        self.assertIn('cannot manage sharing', str(ctx.exception))
        self.assertIn(SA_EMAIL, str(ctx.exception))


@override_settings(GOOGLE_SERVICE_ACCOUNT_JSON=SA_JSON, GOOGLE_SERVICE_ACCOUNT_FILE='')
class GoogleCalendarAclListTests(TestCase):
    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_calendar_id': 'cal-1',
                'google_service_account_json': SA_JSON,
                'google_service_account_email': SA_EMAIL,
            },
        )

    def test_list_shared_emails_paginates_and_skips_non_users(self):
        from apps.core.google_calendar import HttpCalendarClient

        with patch(
            'apps.core.google_calendar._http_json',
            side_effect=[
                {
                    'items': [
                        {'scope': {'type': 'user', 'value': 'ada@gmail.com'}},
                        {'scope': {'type': 'default'}},
                        {'scope': {'type': 'user', 'value': SA_EMAIL}},
                        {'scope': {'type': 'group', 'value': 'group@example.com'}},
                    ],
                    'nextPageToken': 'p2',
                },
                {
                    'items': [
                        {'scope': {'type': 'user', 'value': 'bob@gmail.com'}},
                    ],
                },
            ],
        ) as http:
            emails = HttpCalendarClient(access_token='tok').list_shared_emails()
        self.assertEqual(emails, ['ada@gmail.com', 'bob@gmail.com'])
        self.assertEqual(http.call_count, 2)
        self.assertIn('pageToken=p2', http.call_args_list[1].args[1])


@override_settings(GOOGLE_SERVICE_ACCOUNT_JSON='', GOOGLE_SERVICE_ACCOUNT_FILE='')
class GoogleCalendarServiceAccountTests(TestCase):
    def test_parse_rejects_invalid_json(self):
        from apps.core.google_calendar import GoogleCalendarError, parse_service_account_json

        with self.assertRaises(GoogleCalendarError):
            parse_service_account_json('{')
        with self.assertRaises(GoogleCalendarError):
            parse_service_account_json('{"type":"service_account"}')

    def test_access_token_uses_jwt_bearer(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        from apps.core.google_calendar import JWT_GRANT, service_account_access_token

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        setting, _ = GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_service_account_json': json.dumps({
                    'type': 'service_account',
                    'client_email': SA_EMAIL,
                    'private_key': pem,
                }),
            },
        )
        with patch(
            'apps.core.google_calendar._http_json',
            return_value={'access_token': 'sa-token'},
        ) as mocked:
            token = service_account_access_token(setting)
        self.assertEqual(token, 'sa-token')
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], 'POST')
        self.assertEqual(kwargs['data']['grant_type'], JWT_GRANT)
        self.assertTrue(kwargs['data']['assertion'])

    def test_env_json_overrides_database(self):
        from apps.core.google_calendar import service_account_email

        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_service_account_json': SA_JSON,
                'google_service_account_email': SA_EMAIL,
            },
        )
        with override_settings(GOOGLE_SERVICE_ACCOUNT_JSON=json.dumps({
            'type': 'service_account',
            'client_email': 'env@example.iam.gserviceaccount.com',
            'private_key': '-----BEGIN PRIVATE KEY-----\nenv\n-----END PRIVATE KEY-----\n',
        })):
            self.assertEqual(
                service_account_email(),
                'env@example.iam.gserviceaccount.com',
            )
