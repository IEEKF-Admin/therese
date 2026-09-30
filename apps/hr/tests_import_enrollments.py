"""Read-only import of Calendar, WordPress, and Sympa enrollments."""

from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.core.models import GlobalSetting
from apps.hr.import_enrollments import (
    import_google_calendar,
    import_sympa_csv,
    import_wordpress_sites,
    parse_csv_emails,
)
from apps.hr.models import (
    Employee,
    EmployeeExternalAccount,
    EmployeeWordPressEnrollment,
    WordPressSite,
    Workgroup,
)
from apps.hr.tests_google_calendar import SA_EMAIL, SA_JSON
from apps.hr.wordpress import source_payload


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class RecordingCalendar:
    def __init__(self, emails):
        self.emails = list(emails)
        self.calls = []

    def list_shared_emails(self):
        return list(self.emails)

    def share(self, email, role='writer'):
        self.calls.append(('share', email, role))
        raise AssertionError('share must not run during import')

    def unshare(self, email):
        self.calls.append(('unshare', email))
        raise AssertionError('unshare must not run during import')


class ImportEnrollmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'google_calendar_enabled': True,
                'google_calendar_id': 'cal-1',
                'google_service_account_json': SA_JSON,
                'google_service_account_email': SA_EMAIL,
                'sympa_enabled': True,
                'sympa_robot': 'sympa@listen.uni-bonn.de',
                'sympa_institute_list': 'ieecr@listen.uni-bonn.de',
                'smtp_from_email': 'owner@ieecr-bonn.de',
            },
        )
        self.ada = Employee.objects.create(
            employee_number='IM1',
            first_name='Ada',
            last_name='Lovelace',
            google_account='ada@gmail.com',
            email_professional='ada@uni-bonn.de',
        )
        self.alan = Employee.objects.create(
            employee_number='IM2',
            first_name='Alan',
            last_name='Turing',
            google_account='alan@gmail.com',
            email_professional='alan@uni-bonn.de',
        )
        self.unmatched = Employee.objects.create(
            employee_number='IM3',
            first_name='Grace',
            last_name='Hopper',
            google_account='grace@gmail.com',
            email_professional='grace@uni-bonn.de',
        )
        self.workgroup = Workgroup.objects.create(
            short_name='AG-A',
            long_name='Group A',
            pi=self.ada,
            sympa_list='ag-a@listen.uni-bonn.de',
        )
        self.site = WordPressSite.objects.create(
            name='IEECR',
            url='https://wp.example.org',
            username='therese',
            application_password='app-pass',
        )
        self.site.workgroups.add(self.workgroup)
        self.workgroup.members.add(self.ada)

    def test_parse_csv_emails_is_flexible(self):
        raw = (
            'email,gecos\n'
            'ada@uni-bonn.de,Ada Lovelace\n'
            '"Alan Turing <alan@uni-bonn.de>"\n'
            'not-an-address\n'
        )
        self.assertEqual(
            parse_csv_emails(raw),
            ['ada@uni-bonn.de', 'alan@uni-bonn.de'],
        )

    def test_calendar_import_marks_matches_and_does_not_write(self):
        EmployeeExternalAccount.objects.create(
            employee=self.ada,
            kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
            identifier='ada@gmail.com',
            status=EmployeeExternalAccount.Status.ERROR,
            detail='old',
        )
        EmployeeExternalAccount.objects.create(
            employee=self.unmatched,
            kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
            identifier='grace@gmail.com',
            status=EmployeeExternalAccount.Status.REMOVED,
        )
        duplicate = Employee.objects.create(
            employee_number='IM1b',
            first_name='Ada',
            last_name='Clone',
            google_account='ada@gmail.com',
        )
        fake = RecordingCalendar(['ada@gmail.com', 'alan@gmail.com', SA_EMAIL, 'stranger@gmail.com'])
        with patch('apps.core.wordpress.create_wordpress_post') as create_wp:
            result = import_google_calendar(client=fake)
        self.assertEqual(result['matched'], 3)
        self.assertEqual(result['unmatched'], 1)
        self.assertEqual(fake.calls, [])
        create_wp.assert_not_called()
        for employee in (self.ada, self.alan, duplicate):
            row = EmployeeExternalAccount.objects.get(
                employee=employee,
                kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
            )
            self.assertEqual(row.status, EmployeeExternalAccount.Status.ACTIVE)
            self.assertEqual(row.identifier, 'ada@gmail.com' if employee.google_account == 'ada@gmail.com' else 'alan@gmail.com')
        leftover = EmployeeExternalAccount.objects.get(
            employee=self.unmatched,
            kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
        )
        self.assertEqual(leftover.status, EmployeeExternalAccount.Status.REMOVED)

    def test_wordpress_import_matches_and_does_not_create_posts(self):
        EmployeeWordPressEnrollment.objects.create(
            employee=self.ada,
            site=self.site,
            posttitle='old title',
            status=EmployeeWordPressEnrollment.Status.ERROR,
            last_source={'phone': 'stale'},
            needs_attention=True,
        )
        posts = [
            {'posttitle': 'IM1 Ada Lovelace', 'name': 'Ada Lovelace', 'published': True},
            {'posttitle': 'Different Title', 'name': 'Alan Turing', 'published': True},
            {'posttitle': 'Draft Hopper', 'name': 'Grace Hopper', 'published': False},
            {'posttitle': 'Orphan', 'name': 'Nobody', 'published': True},
        ]

        def fetch(site):
            self.assertEqual(site.pk, self.site.pk)
            return posts

        with patch('apps.core.wordpress.create_wordpress_post') as create_wp:
            with patch('apps.hr.wordpress.create_wordpress_post', create_wp):
                result = import_wordpress_sites(list_posts=fetch)
        create_wp.assert_not_called()
        self.assertEqual(result['matched'], 2)
        self.assertEqual(result['unmatched'], 1)
        ada = EmployeeWordPressEnrollment.objects.get(employee=self.ada, site=self.site)
        self.assertEqual(ada.status, EmployeeWordPressEnrollment.Status.PUBLISHED)
        self.assertEqual(ada.posttitle, 'IM1 Ada Lovelace')
        self.assertEqual(ada.last_source, source_payload(self.ada))
        self.assertFalse(ada.needs_attention)
        alan = EmployeeWordPressEnrollment.objects.get(employee=self.alan, site=self.site)
        self.assertEqual(alan.status, EmployeeWordPressEnrollment.Status.PUBLISHED)
        self.assertEqual(alan.posttitle, 'Different Title')
        self.assertTrue(alan.needs_attention)
        self.assertFalse(
            EmployeeWordPressEnrollment.objects.filter(employee=self.unmatched).exists()
        )

    def test_wordpress_import_skips_ambiguous_names(self):
        Employee.objects.create(
            employee_number='IM4',
            first_name='Alan',
            last_name='Turing',
        )
        posts = [
            {'posttitle': 'Other', 'name': 'Alan Turing', 'published': True},
        ]
        result = import_wordpress_sites(list_posts=lambda site: posts)
        self.assertEqual(result['matched'], 0)
        self.assertEqual(result['unmatched'], 1)
        self.assertFalse(EmployeeWordPressEnrollment.objects.exists())

    def test_sympa_csv_unions_lists_and_does_not_mail(self):
        EmployeeExternalAccount.objects.create(
            employee=self.ada,
            kind=EmployeeExternalAccount.Kind.SYMPA,
            identifier='ada@uni-bonn.de',
            status=EmployeeExternalAccount.Status.ERROR,
            lists=['ieecr@listen.uni-bonn.de'],
        )
        csv = (
            'email,gecos\n'
            'ada@uni-bonn.de,Ada\n'
            'Alan Turing <alan@uni-bonn.de>\n'
            'stranger@uni-bonn.de,X\n'
        )
        with patch('apps.core.sympa.send_sympa_commands') as send:
            with patch('apps.core.sympa.quiet_add') as quiet:
                result = import_sympa_csv('ag-a@listen.uni-bonn.de', csv)
        send.assert_not_called()
        quiet.assert_not_called()
        self.assertEqual(result['matched'], 2)
        self.assertEqual(result['unmatched'], 1)
        ada = EmployeeExternalAccount.objects.get(
            employee=self.ada, kind=EmployeeExternalAccount.Kind.SYMPA,
        )
        self.assertEqual(ada.status, EmployeeExternalAccount.Status.ACTIVE)
        self.assertEqual(
            ada.lists,
            ['ieecr@listen.uni-bonn.de', 'ag-a@listen.uni-bonn.de'],
        )
        alan = EmployeeExternalAccount.objects.get(
            employee=self.alan, kind=EmployeeExternalAccount.Kind.SYMPA,
        )
        self.assertEqual(alan.lists, ['ag-a@listen.uni-bonn.de'])
        self.assertFalse(
            EmployeeExternalAccount.objects.filter(
                employee=self.unmatched, kind=EmployeeExternalAccount.Kind.SYMPA,
            ).exists()
        )


@override_settings(GOOGLE_SERVICE_ACCOUNT_JSON='', GOOGLE_SERVICE_ACCOUNT_FILE='')
class ImportEnrollmentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.admin = _ready('sysadmin-imp')
        self.admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        emp_ct = ContentType.objects.get_for_model(Employee)
        wg_ct = ContentType.objects.get_for_model(Workgroup)
        self.admin.user_permissions.add(
            Permission.objects.get(content_type=emp_ct, codename='can_view_all_employees'),
            Permission.objects.get(content_type=emp_ct, codename='can_view_employees'),
            Permission.objects.get(content_type=wg_ct, codename='manage_working_group'),
        )
        self.hr = _ready('hr-imp')
        self.hr.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'sympa_institute_list': 'ieecr@listen.uni-bonn.de',
            },
        )
        self.employee = Employee.objects.create(
            employee_number='IMV1',
            first_name='Ada',
            last_name='Lovelace',
            google_account='ada@gmail.com',
            email_professional='ada@uni-bonn.de',
        )

    def test_accounts_page_has_import_actions(self):
        self.client.login(username='sysadmin-imp', password='test')
        response = self.client.get(reverse('hr:employee_accounts'))
        self.assertContains(response, 'Import from Google Calendar')
        self.assertContains(response, 'Import from websites')
        self.assertContains(response, 'Import Sympa CSV')
        self.assertContains(response, reverse('hr:employee_accounts_import_calendar'))
        self.assertContains(response, 'ieecr')

    def test_calendar_import_view_marks_without_sharing(self):
        fake = RecordingCalendar(['ada@gmail.com'])
        self.client.login(username='sysadmin-imp', password='test')
        with patch('apps.hr.import_enrollments.get_calendar_client', return_value=fake):
            response = self.client.post(reverse('hr:employee_accounts_import_calendar'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(fake.calls, [])
        row = EmployeeExternalAccount.objects.get(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
        )
        self.assertEqual(row.status, EmployeeExternalAccount.Status.ACTIVE)

    def test_sympa_import_view_reads_csv(self):
        self.client.login(username='sysadmin-imp', password='test')
        uploaded = SimpleUploadedFile(
            'subscribers.csv',
            b'email\nada@uni-bonn.de\n',
            content_type='text/csv',
        )
        with patch('apps.core.sympa.send_sympa_commands') as send:
            response = self.client.post(
                reverse('hr:employee_accounts_import_sympa'),
                {'list_address': 'ieecr@listen.uni-bonn.de', 'csv': uploaded},
            )
        self.assertEqual(response.status_code, 302)
        send.assert_not_called()
        row = EmployeeExternalAccount.objects.get(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.SYMPA,
        )
        self.assertEqual(row.lists, ['ieecr@listen.uni-bonn.de'])

    def test_hr_cannot_import(self):
        self.client.login(username='hr-imp', password='test')
        self.assertEqual(
            self.client.post(reverse('hr:employee_accounts_import_calendar')).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse('hr:employee_accounts_import_websites')).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse('hr:employee_accounts_import_sympa')).status_code,
            403,
        )
