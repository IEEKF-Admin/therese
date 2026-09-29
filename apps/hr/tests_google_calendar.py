"""Google Calendar sharing and the Systemadmin accounts tab."""

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


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


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
                'google_calendar_refresh_token': 'refresh-token',
                'google_calendar_connected_email': 'owner@gmail.com',
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
        GlobalSetting.objects.filter(pk=1).update(google_calendar_refresh_token='')
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
        self.assertContains(response, 'grace@gmail.com')
        self.assertContains(response, 'Hopper')
        self.assertContains(response, 'Shared')

    def test_hr_cannot_open_accounts_tab(self):
        self.client.login(username='hr-gc', password='test')
        listed = self.client.get(reverse('hr:employee_list'))
        self.assertEqual(listed.status_code, 200)
        self.assertNotContains(listed, reverse('hr:employee_accounts'))
        response = self.client.get(reverse('hr:employee_accounts'))
        self.assertEqual(response.status_code, 403)

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
        SITE_URL='https://therese.example.org',
    )
    def test_connect_redirects_to_google(self):
        self.client.login(username='sysadmin-gc', password='test')
        response = self.client.post(reverse('core_settings:google_calendar_connect'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts.google.com', response['Location'])
        self.assertIn('select_account', response['Location'])
        self.assertIn(
            'therese.example.org%2Fsettings%2Fgoogle-calendar%2Fcallback%2F',
            response['Location'],
        )

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='', GOOGLE_OAUTH_CLIENT_SECRET='')
    def test_connect_without_oauth_shows_error(self):
        self.client.login(username='sysadmin-gc', password='test')
        listed = self.client.get(reverse('core_settings:global_settings') + '?tab=integrations')
        self.assertContains(listed, 'Connect Google')
        self.assertContains(listed, 'Save the Google OAuth client ID and secret above')
        response = self.client.post(
            reverse('core_settings:google_calendar_connect'),
            follow=True,
        )
        self.assertContains(
            response,
            'Save the Google OAuth client ID and secret under Integrations first.',
        )

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='',
        GOOGLE_OAUTH_CLIENT_SECRET='',
        SITE_URL='https://therese.example.org',
    )
    def test_connect_with_gui_oauth_redirects(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_oauth_client_id': 'gui-client-id',
                'google_oauth_client_secret': 'gui-client-secret',
            },
        )
        self.client.login(username='sysadmin-gc', password='test')
        response = self.client.post(reverse('core_settings:google_calendar_connect'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts.google.com', response['Location'])
        self.assertIn('gui-client-id', response['Location'])
        self.assertIn(
            'therese.example.org%2Fsettings%2Fgoogle-calendar%2Fcallback%2F',
            response['Location'],
        )

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='env-client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='env-client-secret',
        SITE_URL='https://therese.example.org',
    )
    def test_env_oauth_overrides_gui(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_oauth_client_id': 'gui-client-id',
                'google_oauth_client_secret': 'gui-client-secret',
            },
        )
        self.client.login(username='sysadmin-gc', password='test')
        response = self.client.post(reverse('core_settings:google_calendar_connect'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('env-client-id', response['Location'])
        self.assertNotIn('gui-client-id', response['Location'])


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
                'google_calendar_refresh_token': 'refresh-token',
                'google_calendar_connected_email': 'owner@gmail.com',
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
        self.assertContains(response, 'Calendar connection OK: Institute (as owner@gmail.com).')

    def test_connection_requires_calendar_id(self):
        GlobalSetting.objects.filter(pk=1).update(google_calendar_id='')
        self.client.login(username='sysadmin-gc-test', password='test')
        response = self.client.post(
            reverse('core_settings:google_calendar_test'),
            follow=True,
        )
        self.assertContains(response, 'Set a Google Calendar ID first.')

    def test_connection_requires_google_account(self):
        GlobalSetting.objects.filter(pk=1).update(google_calendar_refresh_token='')
        self.client.login(username='sysadmin-gc-test', password='test')
        response = self.client.post(
            reverse('core_settings:google_calendar_test'),
            follow=True,
        )
        self.assertContains(response, 'Connect a Google account first.')

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

        with patch('apps.core.google_calendar.refresh_access_token', return_value='access'):
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
