from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames
from apps.core.models import GlobalSetting
from apps.holidays.models import (
    HolidayCustomDay,
    HolidayRequest,
    HolidayYearEntitlement,
)
from apps.holidays.public_holidays import public_holidays_for_year
from apps.holidays.services import classify_dates, create_request, remaining_days
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
            employee=self.employee, year=date.today().year, days=Decimal('30'),
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
            employee=other, year=date.today().year, days=Decimal('20'),
        )
        start = date.today()
        while start.weekday() != 0:
            start += timedelta(days=1)
        with self.assertRaises(Exception):
            create_request(other_user, other, [start])


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
            employee=self.employee, year=date.today().year, days=Decimal('30'),
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
