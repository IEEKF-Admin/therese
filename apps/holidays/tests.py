from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames
from apps.core.models import GlobalSetting
from django.core import mail

from apps.holidays.mail import format_holiday_analysis, format_leave_periods
from apps.holidays.models import (
    HolidayCustomDay,
    HolidayEntitlementRate,
    HolidayRequest,
    HolidayYearEntitlement,
)
from apps.holidays.public_holidays import public_holidays_for_year
from apps.holidays.services import (
    cancel_days,
    classify_dates,
    contract_months_in_year,
    create_request,
    remaining_days,
    suggested_entitlement,
)
from apps.hr.models import Contract, Employee, Workgroup


def _user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


def _enable_holidays(*, planning=True, approval=False, gantt=False, module=True):
    setting = GlobalSetting.get_solo()
    setting.holidays_enabled = module
    setting.holidays_planning_enabled = planning
    setting.holidays_approval_enabled = approval
    setting.holidays_gantt_enabled = gantt
    setting.holiday_federal_state = 'NW'
    setting.save()


class HolidayCalculationTests(TestCase):
    def setUp(self):
        _enable_holidays()
        self.user = _user('hol-emp')
        self.employee = Employee.objects.create(
            employee_number='HOL-1',
            first_name='Hanna',
            last_name='Leave',
            user=self.user,
        )
        Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('39.00'),
            valid_from=date(date.today().year, 1, 1),
            valid_until=date(date.today().year, 12, 31),
            is_active=True,
        )
        HolidayYearEntitlement.objects.create(
            employee=self.employee, year=date.today().year, holidays=Decimal('30'),
        )

    def test_public_holidays_include_state_day(self):
        year = date.today().year
        days = public_holidays_for_year(year, 'NW')
        self.assertTrue(any(name == 'Corpus Christi' for name in days.values()))

    def test_weekend_does_not_count(self):
        saturday = date.today()
        while saturday.weekday() != 5:
            saturday += timedelta(days=1)
        _rows, counted = classify_dates(self.employee, saturday, saturday + timedelta(days=1))
        self.assertEqual(counted, [])

    def test_create_counts_weekdays_only(self):
        start = date.today()
        while start.weekday() != 0:
            start += timedelta(days=1)
        days = [start, start + timedelta(days=1), start + timedelta(days=5)]
        request = create_request(self.user, self.employee, days)
        self.assertEqual(request.day_count, Decimal('2'))
        self.assertEqual(request.status, HolidayRequest.Status.APPROVED)

    def test_overlap_blocked(self):
        start = date.today()
        while start.weekday() != 0:
            start += timedelta(days=1)
        create_request(self.user, self.employee, [start])
        with self.assertRaises(Exception):
            create_request(self.user, self.employee, [start])

    def test_brauchtum_except_and(self):
        start = date.today()
        while start.weekday() != 0:
            start += timedelta(days=1)
        mid = start + timedelta(days=1)
        HolidayCustomDay.objects.create(
            year=mid.year, day=mid, name='Bridge',
            mode=HolidayCustomDay.Mode.EXCEPT_AND,
        )
        _rows, counted = classify_dates(
            self.employee, start, start + timedelta(days=2),
            extra_selected={start, mid, start + timedelta(days=2)},
        )
        self.assertIn(mid, counted)

    def test_no_contract_blocks_request(self):
        other_user = _user('hol-none')
        other = Employee.objects.create(
            employee_number='HOL-0', first_name='No', last_name='Contract',
            user=other_user,
        )
        HolidayYearEntitlement.objects.create(
            employee=other, year=date.today().year, holidays=Decimal('20'),
        )
        start = date.today()
        while start.weekday() != 0:
            start += timedelta(days=1)
        with self.assertRaises(Exception):
            create_request(other_user, other, [start])

    def test_zero_entitlement_blocks_planning(self):
        HolidayEntitlementRate.objects.update_or_create(
            weekdays=5, contract_months=12, defaults={'days': Decimal('0')},
        )
        HolidayYearEntitlement.objects.filter(employee=self.employee).update(
            carryover=0, special_leave=0,
        )
        start = date.today() + timedelta(days=1)
        while start.weekday() != 0:
            start += timedelta(days=1)
        with self.assertRaises(Exception):
            create_request(self.user, self.employee, [start])

    def test_carryover_and_special_count_as_available(self):
        HolidayYearEntitlement.objects.filter(employee=self.employee).update(
            carryover=Decimal('2'), special_leave=Decimal('1'),
        )
        start = date.today() + timedelta(days=1)
        while start.weekday() != 0:
            start += timedelta(days=1)
        created = create_request(self.user, self.employee, [start, start + timedelta(days=1)])
        self.assertEqual(created.day_count, Decimal('2'))
        self.assertEqual(remaining_days(self.employee, start.year), Decimal('31'))

    def test_inactive_contract_counts_months(self):
        year = date.today().year
        self.employee.contracts.update(is_active=False)
        self.assertEqual(contract_months_in_year(self.employee, year), 12)
        self.assertEqual(suggested_entitlement(self.employee, year), Decimal('30'))

    def test_holiday_analysis_format(self):
        year = date.today().year
        self.assertEqual(
            format_holiday_analysis(self.employee, [year]),
            f'{year}: verfügbar 30, genehmigt 0, beantragt 0, verbleibend 30',
        )

    def test_cancel_future_days_keeps_rest_and_sends_mail(self):
        self.employee.email_professional = 'hanna@example.com'
        self.employee.save(update_fields=['email_professional'])
        setting = GlobalSetting.get_solo()
        setting.holiday_email_recipients = 'hr@example.com'
        setting.holiday_cancel_email_subject = 'Cancel {{ applicant_name }}'
        setting.holiday_cancel_email_html = '<p>{{ employee_number }} {{ periods }}</p>'
        setting.save()
        start = date.today() + timedelta(days=1)
        while start.weekday() != 0:
            start += timedelta(days=1)
        created = create_request(self.user, self.employee, [start, start + timedelta(days=1)])
        mail.outbox.clear()
        cancelled = cancel_days(self.user, self.employee, [start])
        self.assertEqual(cancelled, [start])
        created.refresh_from_db()
        self.assertEqual(created.counted_dates, [(start + timedelta(days=1)).isoformat()])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Cancel Hanna Leave')
        self.assertIn('hr@example.com', mail.outbox[0].to)
        self.assertIn('hanna@example.com', mail.outbox[0].to)

    def test_format_leave_periods_merges_weekend_gap(self):
        friday = date(2026, 7, 3)
        monday = date(2026, 7, 6)
        self.assertEqual(format_leave_periods([friday, monday]), '03.07.2026 bis 06.07.2026')


class HolidayViewTests(TestCase):
    def setUp(self):
        _enable_holidays(planning=True, approval=True)
        self.user = _user('hol-view')
        self.employee = Employee.objects.create(
            employee_number='HOL-2',
            first_name='Vera',
            last_name='View',
            user=self.user,
        )
        self.approver_user = _user('hol-app')
        self.approver = Employee.objects.create(
            employee_number='HOL-A',
            first_name='Ann',
            last_name='Approve',
            user=self.approver_user,
        )
        wg = Workgroup.objects.create(
            short_name='HOLWG', long_name='Holiday WG', pi=self.approver,
        )
        wg.members.add(self.employee, self.approver)
        group, _ = Group.objects.get_or_create(name=GroupNames.HOLIDAY_APPROVER)
        ct = ContentType.objects.get_for_model(HolidayRequest)
        from django.contrib.auth.models import Permission
        perm = Permission.objects.get(codename='approve_workgroup_holiday', content_type=ct)
        group.permissions.add(perm)
        self.approver_user.groups.add(group)
        Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('39.00'),
            valid_from=date(date.today().year, 1, 1),
            valid_until=date(date.today().year, 12, 31),
            is_active=True,
        )
        HolidayYearEntitlement.objects.create(
            employee=self.employee, year=date.today().year, holidays=Decimal('30'),
        )

    def test_planning_disabled_forbids(self):
        _enable_holidays(planning=False, approval=False)
        self.client.login(username='hol-view', password='test')
        response = self.client.get(reverse('holidays:my_holidays'))
        self.assertEqual(response.status_code, 403)

    def test_module_switch_disables_all_holiday_pages(self):
        _enable_holidays(planning=True, approval=True, gantt=True, module=False)
        self.client.login(username='hol-view', password='test')
        self.assertEqual(self.client.get(reverse('holidays:my_holidays')).status_code, 403)
        self.client.login(username='hol-app', password='test')
        self.assertEqual(self.client.get(reverse('holidays:approve_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('holidays:gantt')).status_code, 403)

    def test_my_holidays_and_submit(self):
        self.client.login(username='hol-view', password='test')
        response = self.client.get(reverse('holidays:my_holidays'))
        self.assertEqual(response.status_code, 200)
        start = date.today()
        while start.weekday() != 0:
            start += timedelta(days=1)
        posted = self.client.post(reverse('holidays:create_request'), {
            'dates': start.isoformat(),
        })
        self.assertEqual(posted.status_code, 302)
        request = HolidayRequest.objects.get()
        self.assertEqual(request.status, HolidayRequest.Status.PENDING)
        self.assertEqual(remaining_days(self.employee, date.today().year), Decimal('29'))

    def test_approver_sees_workgroup_request(self):
        start = date.today()
        while start.weekday() != 0:
            start += timedelta(days=1)
        holiday = create_request(self.user, self.employee, [start])
        self.client.login(username='hol-app', password='test')
        response = self.client.get(reverse('holidays:approve_list'))
        self.assertContains(response, 'Vera View')
        posted = self.client.post(reverse('holidays:approve_list'), {
            'action': 'approve',
            'request_id': str(holiday.pk),
        })
        self.assertEqual(posted.status_code, 302)
        holiday.refresh_from_db()
        self.assertEqual(holiday.status, HolidayRequest.Status.APPROVED)

    def test_my_holidays_tabs_and_no_pdf(self):
        self.client.login(username='hol-view', password='test')
        response = self.client.get(reverse('holidays:my_holidays'))
        self.assertContains(response, 'Request leave')
        self.assertContains(response, 'data-holiday-tab="settings"')
        self.assertContains(response, 'Remaining leave')
        self.assertNotContains(response, 'Entitlement this year')
        self.assertNotContains(response, 'request_pdf')
        self.assertContains(response, 'Cancel holidays')
        self.assertContains(response, 'Granted')
        self.assertContains(response, 'Applied')
        self.assertNotContains(response, 'Add year')

    def test_save_entitlement_table(self):
        self.client.login(username='hol-view', password='test')
        year = date.today().year
        HolidayYearEntitlement.objects.create(
            employee=self.employee, year=year - 1, carryover=Decimal('4'),
        )
        posted = self.client.post(reverse('holidays:my_holidays'), {
            'action': 'save_profile',
            'works_monday': 'on',
            'works_tuesday': 'on',
            'works_wednesday': 'on',
            'works_thursday': 'on',
            'works_friday': 'on',
            'ent_year': [str(year), str(year + 1), str(year + 2), str(year - 1)],
            'ent_carryover': ['2', '0', '9', '8'],
            'ent_special': ['0', '1', '9', '8'],
        })
        self.assertEqual(posted.status_code, 302)
        rows = {
            row.year: row
            for row in HolidayYearEntitlement.objects.filter(employee=self.employee)
        }
        self.assertEqual(rows[year].holidays, Decimal('30'))
        self.assertEqual(rows[year].carryover, Decimal('2'))
        self.assertEqual(rows[year + 1].holidays, Decimal('0'))
        self.assertEqual(rows[year + 1].special_leave, Decimal('1'))
        self.assertEqual(rows[year - 1].carryover, Decimal('4'))
        self.assertNotIn(year + 2, rows)

    def test_settings_shows_past_current_next_year(self):
        year = date.today().year
        HolidayYearEntitlement.objects.create(
            employee=self.employee, year=year - 1, carryover=Decimal('3'),
        )
        self.client.login(username='hol-view', password='test')
        response = self.client.get(reverse('holidays:my_holidays') + '?tab=settings')
        self.assertContains(response, str(year - 1))
        self.assertContains(response, str(year))
        self.assertContains(response, str(year + 1))

    def test_request_email_uses_template_variables(self):
        self.employee.email_professional = 'vera@example.com'
        self.employee.save(update_fields=['email_professional'])
        setting = GlobalSetting.get_solo()
        setting.holiday_email_recipients = 'office@example.com'
        setting.holiday_request_email_subject = 'Leave {{ employee_number }}'
        setting.holiday_request_email_html = '<p>{{ applicant_name }} {{ periods }} {{ holiday_analysis }}</p>'
        setting.save()
        self.client.login(username='hol-view', password='test')
        start = date.today() + timedelta(days=1)
        while start.weekday() != 0:
            start += timedelta(days=1)
        self.client.post(reverse('holidays:create_request'), {'dates': start.isoformat()})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Leave HOL-2')
        self.assertIn('Vera View', mail.outbox[0].body)
        self.assertIn('office@example.com', mail.outbox[0].to)
        self.assertIn('vera@example.com', mail.outbox[0].to)
        self.assertIn(f'{start.year}: verfügbar 30, genehmigt 0, beantragt 1, verbleibend 29', mail.outbox[0].body)

    def test_cancel_view_removes_future_day(self):
        start = date.today() + timedelta(days=1)
        while start.weekday() != 0:
            start += timedelta(days=1)
        created = create_request(self.user, self.employee, [start, start + timedelta(days=1)])
        self.client.login(username='hol-view', password='test')
        posted = self.client.post(reverse('holidays:cancel_days'), {
            'dates': start.isoformat(),
        })
        self.assertEqual(posted.status_code, 302)
        created.refresh_from_db()
        self.assertEqual(created.counted_dates, [(start + timedelta(days=1)).isoformat()])
        self.assertEqual(created.day_count, Decimal('1'))
