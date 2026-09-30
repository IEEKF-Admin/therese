"""Sympa mailing-list enrollment via owner SMTP commands."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.core.models import GlobalSetting
from apps.hr.models import Contract, Employee, EmployeeExternalAccount, Workgroup
from apps.hr.provisioning import sync_employee_sympa, unsubscribe_employee_sympa


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


MAIL = override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_HOST='',
    EMAIL_HOST_USER='',
    EMAIL_HOST_PASSWORD='',
    DEFAULT_FROM_EMAIL='',
)


@MAIL
class SympaProvisioningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'sympa_enabled': True,
                'sympa_robot': 'sympa@listen.uni-bonn.de',
                'sympa_institute_list': 'ieecr@listen.uni-bonn.de',
                'smtp_from_email': 'owner@ieecr-bonn.de',
                'smtp_host': 'smtp.example.org',
            },
        )
        self.employee = Employee.objects.create(
            employee_number='SY1',
            first_name='Ada',
            last_name='Lovelace',
            email_professional='ada@uni-bonn.de',
        )
        Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('39.000'),
            valid_from=date.today() - timedelta(days=10),
            valid_until=None,
            is_active=True,
        )
        self.workgroup = Workgroup.objects.create(
            short_name='AG-A',
            long_name='Group A',
            pi=self.employee,
            sympa_list='ag-a@listen.uni-bonn.de',
        )
        self.workgroup.members.add(self.employee)
        mail.outbox.clear()

    def _body(self):
        return '\n'.join(message.body for message in mail.outbox)

    def test_disabled_does_not_send(self):
        GlobalSetting.objects.filter(pk=1).update(sympa_enabled=False)
        result = sync_employee_sympa(self.employee)
        self.assertEqual(result, 'skipped')
        self.assertEqual(len(mail.outbox), 0)

    def test_add_institute_and_workgroup_lists(self):
        result = sync_employee_sympa(self.employee)
        self.assertEqual(result, 'active')
        body = self._body()
        self.assertIn('QUIET ADD ieecr ada@uni-bonn.de Ada Lovelace', body)
        self.assertIn('QUIET ADD ag-a ada@uni-bonn.de Ada Lovelace', body)
        self.assertEqual(mail.outbox[0].to, ['sympa@listen.uni-bonn.de'])
        self.assertEqual(mail.outbox[0].subject, 'THERESE mailing list update')
        self.assertEqual(mail.outbox[0].from_email, 'owner@ieecr-bonn.de')
        row = EmployeeExternalAccount.objects.get(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.SYMPA,
        )
        self.assertEqual(row.status, EmployeeExternalAccount.Status.ACTIVE)
        self.assertEqual(row.identifier, 'ada@uni-bonn.de')
        self.assertEqual(
            row.lists,
            ['ieecr@listen.uni-bonn.de', 'ag-a@listen.uni-bonn.de'],
        )

    def test_replace_when_professional_email_changes(self):
        sync_employee_sympa(self.employee)
        mail.outbox.clear()
        self.employee.email_professional = 'ada.new@uni-bonn.de'
        self.employee.save()
        result = sync_employee_sympa(self.employee)
        self.assertEqual(result, 'active')
        body = self._body()
        self.assertIn('QUIET DELETE ieecr ada@uni-bonn.de', body)
        self.assertIn('QUIET DELETE ag-a ada@uni-bonn.de', body)
        self.assertIn('QUIET ADD ieecr ada.new@uni-bonn.de Ada Lovelace', body)
        row = EmployeeExternalAccount.objects.get(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.SYMPA,
        )
        self.assertEqual(row.identifier, 'ada.new@uni-bonn.de')

    def test_workgroup_change_updates_lists(self):
        sync_employee_sympa(self.employee)
        mail.outbox.clear()
        other = Employee.objects.create(
            employee_number='SY1b',
            first_name='Other',
            last_name='Pi',
        )
        wg2 = Workgroup.objects.create(
            short_name='AG-B',
            long_name='Group B',
            pi=other,
            sympa_list='ag-b@listen.uni-bonn.de',
        )
        self.workgroup.members.remove(self.employee)
        wg2.members.add(self.employee)
        result = sync_employee_sympa(self.employee)
        self.assertEqual(result, 'active')
        body = self._body()
        self.assertIn('QUIET DELETE ag-a ada@uni-bonn.de', body)
        self.assertIn('QUIET ADD ag-b ada@uni-bonn.de Ada Lovelace', body)
        self.assertNotIn('QUIET ADD ieecr', body)

    def test_unsub_when_archived(self):
        sync_employee_sympa(self.employee)
        mail.outbox.clear()
        contract = self.employee.contracts.get()
        contract.valid_until = date.today() - timedelta(days=1)
        contract.save()
        result = sync_employee_sympa(self.employee)
        self.assertEqual(result, 'removed')
        body = self._body()
        self.assertIn('QUIET DELETE ieecr ada@uni-bonn.de', body)
        self.assertIn('QUIET DELETE ag-a ada@uni-bonn.de', body)
        row = EmployeeExternalAccount.objects.get(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.SYMPA,
        )
        self.assertEqual(row.status, EmployeeExternalAccount.Status.REMOVED)
        self.assertEqual(row.identifier, 'ada@uni-bonn.de')
        self.assertEqual(row.lists, [])

    def test_externals_are_skipped(self):
        self.employee.is_external = True
        self.employee.save(update_fields=['is_external'])
        result = sync_employee_sympa(self.employee)
        self.assertEqual(result, 'skipped')
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(
            EmployeeExternalAccount.objects.filter(
                employee=self.employee,
                kind=EmployeeExternalAccount.Kind.SYMPA,
            ).exists()
        )

    def test_no_professional_email_does_not_create_row(self):
        empty = Employee.objects.create(
            employee_number='SY0',
            first_name='No',
            last_name='Mail',
        )
        result = sync_employee_sympa(empty)
        self.assertEqual(result, 'skipped')
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(
            EmployeeExternalAccount.objects.filter(employee=empty).exists()
        )

    def test_delete_unsubscribes_even_when_disabled(self):
        sync_employee_sympa(self.employee)
        mail.outbox.clear()
        GlobalSetting.objects.filter(pk=1).update(sympa_enabled=False)
        unsubscribe_employee_sympa(self.employee)
        body = self._body()
        self.assertIn('QUIET DELETE ieecr ada@uni-bonn.de', body)
        self.assertIn('QUIET DELETE ag-a ada@uni-bonn.de', body)

    def test_save_schedules_sync(self):
        mail.outbox.clear()
        emp = Employee(
            employee_number='SY2',
            first_name='Alan',
            last_name='Turing',
            email_professional='alan@uni-bonn.de',
        )
        with self.captureOnCommitCallbacks(execute=True):
            emp.save()
            Contract.objects.create(
                employee=emp,
                weekly_hours=Decimal('20.000'),
                valid_from=date.today(),
                is_active=True,
            )
        self.assertIn('QUIET ADD ieecr alan@uni-bonn.de Alan Turing', self._body())


@MAIL
class SympaAccountsAndSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.admin = _ready('sysadmin-sy')
        self.admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        emp_ct = ContentType.objects.get_for_model(Employee)
        wg_ct = ContentType.objects.get_for_model(Workgroup)
        self.admin.user_permissions.add(
            Permission.objects.get(content_type=emp_ct, codename='can_view_all_employees'),
            Permission.objects.get(content_type=emp_ct, codename='can_view_employees'),
            Permission.objects.get(content_type=wg_ct, codename='manage_working_group'),
        )
        self.hr = _ready('hr-sy')
        self.hr.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        self.employee = Employee.objects.create(
            employee_number='SY3',
            first_name='Grace',
            last_name='Hopper',
            email_professional='grace@uni-bonn.de',
        )
        EmployeeExternalAccount.objects.create(
            employee=self.employee,
            kind=EmployeeExternalAccount.Kind.SYMPA,
            identifier='grace@uni-bonn.de',
            status=EmployeeExternalAccount.Status.ACTIVE,
            lists=['ieecr@listen.uni-bonn.de'],
        )
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'sympa_enabled': True,
                'sympa_robot': 'sympa@listen.uni-bonn.de',
                'sympa_institute_list': 'ieecr@listen.uni-bonn.de',
                'smtp_from_email': 'owner@ieecr-bonn.de',
                'smtp_host': 'smtp.example.org',
            },
        )
        self.workgroup = Workgroup.objects.create(
            short_name='AG-S',
            long_name='Sympa WG',
            pi=self.employee,
        )
        mail.outbox.clear()

    def test_accounts_shows_professional_email_and_lists(self):
        self.client.login(username='sysadmin-sy', password='test')
        response = self.client.get(reverse('hr:employee_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sympa')
        self.assertContains(response, 'grace@uni-bonn.de')
        self.assertContains(response, 'ieecr@listen.uni-bonn.de')
        self.assertContains(response, 'Shared')

    def test_accounts_shows_current_professional_email(self):
        self.employee.email_professional = 'grace.new@uni-bonn.de'
        self.employee.save(update_fields=['email_professional'])
        self.client.login(username='sysadmin-sy', password='test')
        response = self.client.get(reverse('hr:employee_accounts'))
        self.assertContains(response, 'grace.new@uni-bonn.de')
        self.assertNotContains(response, 'grace@uni-bonn.de')

    def test_save_workgroup_mapping(self):
        self.client.login(username='sysadmin-sy', password='test')
        posted = self.client.post(reverse('core_settings:global_settings'), {
            'action': 'save_integrations',
            'smtp_port': '465',
            'smtp_use_ssl': 'on',
            'smtp_from_email': 'owner@ieecr-bonn.de',
            'sympa_enabled': 'on',
            'sympa_robot': 'sympa@listen.uni-bonn.de',
            'sympa_institute_list': 'ieecr@listen.uni-bonn.de',
            f'sympa_wg_{self.workgroup.pk}': 'ag-s@listen.uni-bonn.de',
        })
        self.assertEqual(posted.status_code, 302)
        self.workgroup.refresh_from_db()
        self.assertEqual(self.workgroup.sympa_list, 'ag-s@listen.uni-bonn.de')

    def test_test_sends_help(self):
        self.client.login(username='sysadmin-sy', password='test')
        response = self.client.post(reverse('core_settings:sympa_test'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sent HELP to sympa@listen.uni-bonn.de')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('HELP', mail.outbox[0].body)

    def test_sync_all_requires_enabled(self):
        GlobalSetting.objects.filter(pk=1).update(sympa_enabled=False)
        self.client.login(username='sysadmin-sy', password='test')
        response = self.client.post(reverse('core_settings:sympa_sync_all'), follow=True)
        self.assertContains(response, 'Enable Sympa mailing lists before syncing.')

    def test_hr_cannot_test(self):
        self.client.login(username='hr-sy', password='test')
        response = self.client.post(reverse('core_settings:sympa_test'))
        self.assertEqual(response.status_code, 403)
