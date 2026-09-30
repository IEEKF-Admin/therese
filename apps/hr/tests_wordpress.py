"""WordPress THERESE Sync client, accounts marks, and workgroup assignment."""

import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.login_popups import evaluate_login_popups
from apps.accounts.models import CustomUser, LoginPopupConfig
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.accounts.template_variables import (
    build_replacement_map,
    catalog_for_trigger,
    render_placeholders,
)
from apps.core.models import GlobalSetting
from apps.hr.models import (
    Building,
    Contract,
    Employee,
    EmployeeWordPressEnrollment,
    Room,
    WordPressSite,
    Workgroup,
)
from apps.hr.wordpress import (
    WP_QUEUE_SESSION,
    employee_assigned_to_site,
    employee_wordpress_states,
    publish_employee_to_site,
    source_payload,
    unpublish_employee_from_site,
    wordpress_attention_exists,
)


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = json.dumps(payload).encode('utf-8')
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeWP:
    def __init__(self):
        self.calls = []
        self.payloads = {
            '/status': {'ok': True, 'post_type': 'member'},
            '/posts': {'id': 9, 'posttitle': 'WP1 Ada Lovelace', 'published': True},
            '/posts/update': {'id': 9, 'posttitle': 'WP1 Ada Lovelace', 'published': True},
            '/posts/unpublish': {'id': 9, 'posttitle': 'WP1 Ada Lovelace', 'published': False},
        }

    def urlopen(self, req, timeout=None, context=None):
        url = req.full_url
        path = url.split('/wp-json/therese/v1', 1)[-1].split('?', 1)[0]
        self.calls.append({
            'method': req.get_method(),
            'url': url,
            'path': path,
            'headers': dict(req.header_items()),
        })
        if not url.startswith('https://'):
            raise AssertionError('WordPress client must use HTTPS')
        payload = self.payloads.get(path)
        if payload is None:
            raise HTTPError(url, 404, 'Not Found', hdrs=None, fp=BytesIO(b'{"message":"missing"}'))
        return FakeResponse(payload)


@override_settings(EMAIL_HOST='', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class WordPressClientTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={'wordpress_positions': 'PI\nPostdoc'},
        )
        self.building = Building.objects.create(
            number='B-WP',
            name='Main',
            address='Nussallee 14\n53115 Bonn',
        )
        self.room = Room.objects.create(building=self.building, room_number='1.01')
        self.employee = Employee.objects.create(
            employee_number='WP1',
            first_name='Ada',
            last_name='Lovelace',
            email_professional='ada@uni-bonn.de',
            phone_number='0228-1',
            private_phone_number='0171-1',
            website='https://example.org/ada',
            room=self.room,
        )
        Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('39.000'),
            valid_from=date.today() - timedelta(days=10),
            valid_until=None,
            is_active=True,
        )
        self.workgroup = Workgroup.objects.create(
            short_name='AG-WP',
            long_name='WordPress Group',
            pi=self.employee,
        )
        self.site = WordPressSite.objects.create(
            name='IEECR',
            url='https://wp.example.org',
            username='therese',
            application_password='app-pass',
        )
        self.site.workgroups.add(self.workgroup)
        self.admin = _ready('sysadmin-wp')
        self.admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        emp_ct = ContentType.objects.get_for_model(Employee)
        wg_ct = ContentType.objects.get_for_model(Workgroup)
        self.admin.user_permissions.add(
            Permission.objects.get(content_type=emp_ct, codename='can_view_all_employees'),
            Permission.objects.get(content_type=emp_ct, codename='can_view_employees'),
            Permission.objects.get(content_type=wg_ct, codename='manage_working_group'),
        )
        self.hr = _ready('hr-wp')
        self.hr.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        self.client = Client()
        self.wp = FakeWP()

    def _states(self):
        employee = (
            Employee.objects.select_related('room__building')
            .prefetch_related('workgroups', 'wordpress_enrollments')
            .get(pk=self.employee.pk)
        )
        site = WordPressSite.objects.prefetch_related('workgroups').get(pk=self.site.pk)
        return employee_wordpress_states(employee, [site])[0]

    def test_assignment_via_workgroup_only(self):
        self.assertFalse(employee_assigned_to_site(self.employee, self.site))
        self.assertEqual(self._states()['label'], '—')
        self.workgroup.members.add(self.employee)
        self.employee.refresh_from_db()
        self.assertTrue(employee_assigned_to_site(
            Employee.objects.prefetch_related('workgroups').get(pk=self.employee.pk),
            WordPressSite.objects.prefetch_related('workgroups').get(pk=self.site.pk),
        ))
        self.assertEqual(self._states()['action'], 'add')
        self.assertFalse(self._states()['marked'])
        self.assertFalse(EmployeeWordPressEnrollment.objects.exists())

    def test_address_comes_from_building(self):
        payload = source_payload(
            Employee.objects.select_related('room__building').get(pk=self.employee.pk)
        )
        self.assertEqual(payload['address'], 'Nussallee 14\n53115 Bonn')
        self.assertEqual(payload['name'], 'Ada Lovelace')
        self.assertEqual(payload['posttitle'], 'WP1 Ada Lovelace')
        self.assertEqual(payload['phone'], '0228-1')
        self.assertEqual(payload['mobile'], '0171-1')
        self.assertEqual(payload['email'], 'ada@uni-bonn.de')
        self.assertEqual(payload['linkmember'], 'https://example.org/ada')

    def test_source_change_marks_update_needed(self):
        self.workgroup.members.add(self.employee)
        employee = Employee.objects.select_related('room__building').get(pk=self.employee.pk)
        EmployeeWordPressEnrollment.objects.create(
            employee=self.employee,
            site=self.site,
            posttitle='WP1 Ada Lovelace',
            status=EmployeeWordPressEnrollment.Status.PUBLISHED,
            last_source=source_payload(employee),
            last_sent={'name': 'Ada Lovelace', 'position': 'PI'},
        )
        self.employee.first_name = 'Ada Augusta'
        self.employee.save(update_fields=['first_name'])
        enrollment = EmployeeWordPressEnrollment.objects.get(employee=self.employee, site=self.site)
        self.assertTrue(enrollment.needs_attention)
        state = self._states()
        self.assertEqual(state['label'], 'Update needed')
        self.assertTrue(state['marked'])
        self.assertIn('name', state['changed_fields'])
        self.assertTrue(wordpress_attention_exists())

    def test_leaving_workgroup_marks_unpublish(self):
        self.workgroup.members.add(self.employee)
        employee = Employee.objects.select_related('room__building').get(pk=self.employee.pk)
        EmployeeWordPressEnrollment.objects.create(
            employee=self.employee,
            site=self.site,
            posttitle='WP1 Ada Lovelace',
            status=EmployeeWordPressEnrollment.Status.PUBLISHED,
            last_source=source_payload(employee),
        )
        self.workgroup.members.remove(self.employee)
        enrollment = EmployeeWordPressEnrollment.objects.get(employee=self.employee, site=self.site)
        self.assertTrue(enrollment.needs_attention)
        self.assertEqual(self._states()['action'], 'unpublish')
        self.assertEqual(self._states()['label'], 'Unpublish')

    @patch('apps.core.wordpress.urlopen')
    def test_publish_and_unpublish_do_not_write_employee(self, urlopen):
        urlopen.side_effect = self.wp.urlopen
        self.workgroup.members.add(self.employee)
        employee = (
            Employee.objects.select_related('room__building')
            .prefetch_related('workgroups')
            .get(pk=self.employee.pk)
        )
        site = WordPressSite.objects.prefetch_related('workgroups').get(pk=self.site.pk)
        publish_employee_to_site(employee, site, {
            'posttitle': 'WP1 Ada Lovelace',
            'name': 'Published Name',
            'position': 'PI',
            'phone': '0228-1',
            'mobile': '0171-1',
            'email': 'ada@uni-bonn.de',
            'address': 'Nussallee 14\n53115 Bonn',
            'linkmember': 'https://example.org/ada',
            'websideadressfield': 'Lab',
            'linkfieldaddress': 'https://maps.example',
        })
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, 'Ada')
        self.assertEqual(self.employee.last_name, 'Lovelace')
        enrollment = EmployeeWordPressEnrollment.objects.get(employee=self.employee, site=self.site)
        self.assertEqual(enrollment.status, EmployeeWordPressEnrollment.Status.PUBLISHED)
        self.assertEqual(enrollment.last_sent['name'], 'Published Name')
        self.assertEqual(enrollment.last_sent['position'], 'PI')
        self.assertFalse(enrollment.needs_attention)
        paths = [call['path'] for call in self.wp.calls]
        self.assertIn('/posts', paths)
        unpublish_employee_from_site(employee, site)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, EmployeeWordPressEnrollment.Status.UNPUBLISHED)
        self.assertIn('/posts/unpublish', [call['path'] for call in self.wp.calls])

    @patch('apps.core.wordpress.urlopen')
    def test_accounts_add_and_red_dot_for_systemadmin_only(self, urlopen):
        urlopen.side_effect = self.wp.urlopen
        self.workgroup.members.add(self.employee)
        self.client.login(username='sysadmin-wp', password='test')
        listed = self.client.get(reverse('hr:employee_list'))
        self.assertEqual(listed.status_code, 200)
        self.assertContains(listed, 'Accounts')
        self.assertNotContains(listed, 'aria-label="WordPress updates needed"')
        accounts = self.client.get(reverse('hr:employee_accounts'))
        self.assertEqual(accounts.status_code, 200)
        self.assertContains(accounts, 'Website')
        self.assertNotContains(accounts, 'Beck Group')
        self.assertContains(accounts, 'IEECR')
        self.assertContains(accounts, 'aria-label="Add"')
        self.assertContains(accounts, 'name="selected_ids"')
        self.assertContains(accounts, 'Add to websites')
        self.assertContains(accounts, 'Remove from websites')
        self.assertNotContains(accounts, 'wp-open-publish')
        posted = self.client.post(reverse('hr:employee_wordpress_publish'), {
            'employee': str(self.employee.pk),
            'site': str(self.site.pk),
            'posttitle': 'WP1 Ada Lovelace',
            'name': 'Ada Lovelace',
            'position': 'Postdoc',
            'phone': '0228-1',
            'mobile': '0171-1',
            'email': 'ada@uni-bonn.de',
            'address': 'Nussallee 14\n53115 Bonn',
            'linkmember': 'https://example.org/ada',
            'websideadressfield': '',
            'linkfieldaddress': '',
        })
        self.assertEqual(posted.status_code, 302)
        self.employee.phone_number = '0228-9'
        self.employee.save(update_fields=['phone_number'])
        listed = self.client.get(reverse('hr:employee_list'))
        self.assertContains(listed, 'aria-label="WordPress updates needed"')
        accounts = self.client.get(reverse('hr:employee_accounts'))
        self.assertContains(accounts, 'Update needed')
        self.assertContains(accounts, 'accounts-row-attention')
        self.client.logout()
        self.client.login(username='hr-wp', password='test')
        listed = self.client.get(reverse('hr:employee_list'))
        self.assertEqual(listed.status_code, 200)
        self.assertNotContains(listed, reverse('hr:employee_accounts'))
        self.assertNotContains(listed, 'aria-label="WordPress updates needed"')
        self.assertEqual(self.client.get(reverse('hr:employee_accounts')).status_code, 403)

    def test_accounts_shows_multiple_sites_in_website_column(self):
        self.workgroup.members.add(self.employee)
        other = WordPressSite.objects.create(
            name='Beck Lab',
            url='https://beck.example.org',
            username='therese',
            application_password='app-pass',
        )
        other.workgroups.add(self.workgroup)
        self.client.login(username='sysadmin-wp', password='test')
        accounts = self.client.get(reverse('hr:employee_accounts'))
        self.assertContains(accounts, 'Website')
        self.assertContains(accounts, 'IEECR')
        self.assertContains(accounts, 'Beck Lab')
        self.assertContains(accounts, 'accounts-site-line', count=2)
        self.assertNotContains(accounts, 'wp-open-publish')

    def test_bulk_website_add_queues_dialogs_and_publish_pops(self):
        self.workgroup.members.add(self.employee)
        other = WordPressSite.objects.create(
            name='Beck Lab',
            url='https://beck.example.org',
            username='therese',
            application_password='app-pass',
        )
        other.workgroups.add(self.workgroup)
        self.client.login(username='sysadmin-wp', password='test')
        queued = self.client.post(reverse('hr:employee_accounts_bulk'), {
            'action': 'website_add',
            'selected_ids': [str(self.employee.pk)],
        })
        self.assertEqual(queued.status_code, 302)
        queue = self.client.session[WP_QUEUE_SESSION]
        self.assertEqual(len(queue), 2)
        site_ids = {item['site'] for item in queue}
        self.assertEqual(site_ids, {self.site.pk, other.pk})
        first = queue[0]
        with patch('apps.core.wordpress.urlopen', side_effect=self.wp.urlopen):
            posted = self.client.post(reverse('hr:employee_wordpress_publish'), {
                'employee': str(first['employee']),
                'site': str(first['site']),
                'posttitle': 'WP1 Ada Lovelace',
                'name': 'Ada Lovelace',
                'position': 'PI',
                'phone': '0228-1',
                'mobile': '0171-1',
                'email': 'ada@uni-bonn.de',
                'address': 'Nussallee 14\n53115 Bonn',
                'linkmember': 'https://example.org/ada',
            })
        self.assertEqual(posted.status_code, 302)
        remaining = self.client.session[WP_QUEUE_SESSION]
        self.assertEqual(len(remaining), 1)
        self.assertNotEqual(remaining[0]['site'], first['site'])

    def test_bulk_website_remove_unpublishes(self):
        self.workgroup.members.add(self.employee)
        employee = Employee.objects.select_related('room__building').get(pk=self.employee.pk)
        EmployeeWordPressEnrollment.objects.create(
            employee=self.employee,
            site=self.site,
            posttitle='WP1 Ada Lovelace',
            status=EmployeeWordPressEnrollment.Status.PUBLISHED,
            last_source=source_payload(employee),
        )
        self.client.login(username='sysadmin-wp', password='test')
        with patch('apps.core.wordpress.urlopen', side_effect=self.wp.urlopen):
            removed = self.client.post(reverse('hr:employee_accounts_bulk'), {
                'action': 'website_remove',
                'selected_ids': [str(self.employee.pk)],
            })
        self.assertEqual(removed.status_code, 302)
        enrollment = EmployeeWordPressEnrollment.objects.get(
            employee=self.employee, site=self.site,
        )
        self.assertEqual(enrollment.status, EmployeeWordPressEnrollment.Status.UNPUBLISHED)
        self.assertIn('/posts/unpublish', [call['path'] for call in self.wp.calls])

    def test_bulk_website_queue_cancel(self):
        self.workgroup.members.add(self.employee)
        self.client.login(username='sysadmin-wp', password='test')
        self.client.post(reverse('hr:employee_accounts_bulk'), {
            'action': 'website_add',
            'selected_ids': [str(self.employee.pk)],
        })
        self.assertTrue(self.client.session.get(WP_QUEUE_SESSION))
        cancelled = self.client.post(reverse('hr:employee_accounts_bulk'), {
            'action': 'website_queue_cancel',
        })
        self.assertEqual(cancelled.status_code, 302)
        self.assertFalse(self.client.session.get(WP_QUEUE_SESSION))

    def test_save_sites_and_positions_https_only(self):
        self.client.login(username='sysadmin-wp', password='test')
        posted = self.client.post(reverse('core_settings:global_settings'), {
            'action': 'save_integrations',
            'smtp_port': '465',
            'smtp_use_ssl': 'on',
            'wordpress_positions': 'Group leader\nTechnician',
            'wp_sites_present': '1',
            'wp_site_0_id': str(self.site.pk),
            'wp_site_0_name': 'IEECR',
            'wp_site_0_url': 'https://wp.example.org',
            'wp_site_0_username': 'therese',
            'wp_site_0_password': '',
            'wp_site_0_workgroups': [str(self.workgroup.pk)],
            'wp_site_1_id': '',
            'wp_site_1_name': 'HTTP Site',
            'wp_site_1_url': 'http://insecure.example.org',
            'wp_site_1_username': 'x',
            'wp_site_1_password': 'y',
        })
        self.assertEqual(posted.status_code, 302)
        setting = GlobalSetting.get_solo()
        self.assertEqual(setting.wordpress_positions, 'Group leader\nTechnician')
        self.site.refresh_from_db()
        self.assertEqual(self.site.application_password, 'app-pass')
        self.assertFalse(WordPressSite.objects.filter(url='http://insecure.example.org').exists())
        posted = self.client.post(reverse('core_settings:global_settings'), {
            'action': 'save_integrations',
            'smtp_port': '465',
            'smtp_use_ssl': 'on',
            'wordpress_positions': 'Group leader',
        })
        self.assertEqual(posted.status_code, 302)
        self.assertTrue(WordPressSite.objects.filter(pk=self.site.pk).exists())

    @patch('apps.core.wordpress.urlopen')
    def test_connection_probe(self, urlopen):
        urlopen.side_effect = self.wp.urlopen
        self.client.login(username='sysadmin-wp', password='test')
        response = self.client.post(
            reverse('core_settings:wordpress_test', args=[self.site.pk]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'WordPress connection OK')
        self.assertEqual(self.wp.calls[0]['path'], '/status')

    def test_messaging_variables_and_login_popup(self):
        self.admin.email = 'sysadmin-wp@example.org'
        self.admin.save(update_fields=['email'])
        config = LoginPopupConfig.objects.create(
            name='WP update',
            trigger='wordpress_update_needed',
            text='Update {{ wordpress_employee_name }} on {{ wordpress_site_name }}',
            enabled=True,
            show_popup=True,
            send_email=True,
            email_subject='WP {{ wordpress_reason }}',
            email_html='<p>{{ wordpress_updates }}</p>',
            link_to='employee_accounts',
        )
        config.target_users.add(self.admin)
        self.workgroup.members.add(self.employee)
        employee = Employee.objects.select_related('room__building').get(pk=self.employee.pk)
        EmployeeWordPressEnrollment.objects.create(
            employee=self.employee,
            site=self.site,
            posttitle='WP1 Ada Lovelace',
            status=EmployeeWordPressEnrollment.Status.PUBLISHED,
            last_source=source_payload(employee),
        )
        self.employee.first_name = 'Ada Augusta'
        self.employee.save(update_fields=['first_name'])
        keys = {item['key'] for item in catalog_for_trigger('wordpress_update_needed')}
        self.assertIn('wordpress_site_name', keys)
        self.assertIn('wordpress_updates', keys)
        replacements = build_replacement_map(
            self.admin,
            None,
            wordpress_item={
                'employee': self.employee,
                'site': self.site,
                'reason': 'Update needed',
                'changed_fields': 'name',
            },
        )
        rendered = render_placeholders(
            '{{ wordpress_employee_name }} {{ wordpress_site_name }} {{ wordpress_reason }}',
            replacements,
        )
        self.assertIn('Ada Augusta', rendered)
        self.assertIn('IEECR', rendered)
        self.assertIn('Update needed', rendered)
        popups = evaluate_login_popups(self.admin)
        self.assertTrue(popups)
        self.assertIn('Ada Augusta', popups[0]['text'])
        self.assertEqual(popups[0]['link'], 'employee_accounts')
        subjects = [message.subject for message in mail.outbox]
        self.assertTrue(any('Update needed' in subject for subject in subjects), subjects)
