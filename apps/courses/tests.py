from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.login_popups import evaluate_login_popups
from apps.accounts.models import CustomUser, LoginPopupConfig
from apps.accounts.permissions import (
    GroupNames,
    assign_permissions_to_groups,
    get_or_create_default_groups,
)
from apps.accounts.template_variables import catalog_for_trigger
from apps.courses.access import (
    user_can_access_hub,
    user_can_write_employee_course,
    visible_courses_for_user,
    visible_employees_for_course,
)
from apps.courses.models import Course, CourseCompletion, CourseManager
from apps.courses.services import (
    STATUS_DUE,
    STATUS_OK,
    STATUS_WARN,
    add_calendar_months,
    completion_status,
    required_employees,
)
from apps.hr.models import Contract, Employee, Workgroup


def _ready(username, *, superuser=False):
    create = CustomUser.objects.create_superuser if superuser else CustomUser.objects.create_user
    user = create(username, password='test', email=f'{username}@example.org')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


def _employee(number, first, last, user=None, **kwargs):
    return Employee.objects.create(
        employee_number=number,
        first_name=first,
        last_name=last,
        user=user,
        **kwargs,
    )


def _contract(employee, **kwargs):
    defaults = {
        'weekly_hours': Decimal('39.000'),
        'valid_from': date(2020, 1, 1),
        'is_active': True,
    }
    defaults.update(kwargs)
    return Contract.objects.create(employee=employee, **defaults)


def _pdf(name='cert.pdf'):
    return SimpleUploadedFile(name, b'%PDF-1.4 test', content_type='application/pdf')


class CoursesBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.pi = _employee('PI-C', 'Pat', 'Investigator')
        self.wg_a = Workgroup.objects.create(short_name='C-A', long_name='Course A', pi=self.pi)
        self.wg_b = Workgroup.objects.create(short_name='C-B', long_name='Course B', pi=self.pi)


class RequiredEmployeesTests(CoursesBase):
    def test_union_dedupes_and_skips_externals_from_institute(self):
        today = date.today()
        inst = _employee('C-IN', 'In', 'Stitute')
        _contract(inst, valid_from=today - timedelta(days=10), valid_until=today + timedelta(days=10))
        intern = _employee('C-INT', 'No', 'Contract')
        external = _employee('C-EX', 'Ex', 'Ternal', is_external=True)
        wg_member = _employee('C-WG', 'Work', 'Group')
        extra = _employee('C-EX2', 'Extra', 'Person')
        both = inst
        self.wg_a.members.add(wg_member, both)

        course = Course.objects.create(
            name='Safety',
            all_institute=True,
        )
        course.workgroups.add(self.wg_a)
        course.extra_employees.add(intern, extra, external, both)

        pks = set(required_employees(course, as_of=today).values_list('pk', flat=True))
        self.assertIn(inst.pk, pks)
        self.assertIn(wg_member.pk, pks)
        self.assertIn(intern.pk, pks)
        self.assertIn(extra.pk, pks)
        self.assertIn(external.pk, pks)
        self.assertEqual(len(pks), 5)

        expired = _employee('C-OLD', 'Old', 'Contract')
        _contract(expired, valid_from=today - timedelta(days=400), valid_until=today - timedelta(days=1))
        pks2 = set(required_employees(course, as_of=today).values_list('pk', flat=True))
        self.assertNotIn(expired.pk, pks2)


class CompletionStatusTests(TestCase):
    def test_never_completed_is_due(self):
        course = Course.objects.create(name='Once')
        emp = _employee('ST-1', 'A', 'B')
        row = completion_status(course, emp, today=date(2026, 6, 1))
        self.assertEqual(row['status'], STATUS_DUE)
        self.assertIsNone(row['due_date'])
        self.assertTrue(row['needs_attention'])

    def test_one_time_completed_is_ok(self):
        course = Course.objects.create(name='Once')
        emp = _employee('ST-2', 'A', 'B')
        CourseCompletion.objects.create(course=course, employee=emp, completed_on=date(2026, 1, 1))
        row = completion_status(course, emp, today=date(2026, 6, 1))
        self.assertEqual(row['status'], STATUS_OK)
        self.assertFalse(row['needs_attention'])

    def test_recurring_month_end_clamp_and_due_on_due_date(self):
        self.assertEqual(add_calendar_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        course = Course.objects.create(name='Yearly', interval_months=12, warn_weeks=4)
        emp = _employee('ST-3', 'A', 'B')
        CourseCompletion.objects.create(course=course, employee=emp, completed_on=date(2026, 1, 15))
        next_due = date(2027, 1, 15)
        self.assertEqual(
            completion_status(course, emp, today=date(2026, 12, 1))['status'],
            STATUS_OK,
        )
        self.assertEqual(
            completion_status(course, emp, today=date(2026, 12, 18))['status'],
            STATUS_WARN,
        )
        self.assertEqual(
            completion_status(course, emp, today=next_due)['status'],
            STATUS_DUE,
        )

    def test_empty_warn_weeks_has_no_warn_window(self):
        course = Course.objects.create(name='Yearly', interval_months=12, warn_weeks=None)
        emp = _employee('ST-4', 'A', 'B')
        CourseCompletion.objects.create(course=course, employee=emp, completed_on=date(2026, 1, 15))
        self.assertEqual(
            completion_status(course, emp, today=date(2027, 1, 14))['status'],
            STATUS_OK,
        )
        self.assertEqual(
            completion_status(course, emp, today=date(2027, 1, 15))['status'],
            STATUS_DUE,
        )


class CourseAccessTests(CoursesBase):
    def setUp(self):
        super().setUp()
        self.admin = _ready('c-admin', superuser=True)
        self.inst_user = _ready('c-inst')
        self.inst_user.groups.add(Group.objects.get(name=GroupNames.COURSES_SEE_LISTS_INSTITUTE))
        self.wg_user = _ready('c-wg')
        self.wg_user.groups.add(Group.objects.get(name=GroupNames.COURSES_SEE_LISTS_WORKGROUP))
        self.mgr_user = _ready('c-mgr')
        self.self_user = _ready('c-self')

        self.inst_emp = _employee('C-IE', 'Inst', 'Viewer', user=self.inst_user)
        self.wg_emp = _employee('C-WE', 'Wg', 'Viewer', user=self.wg_user)
        self.mgr_emp = _employee('C-ME', 'Mgr', 'Person', user=self.mgr_user)
        self.self_emp = _employee('C-SE', 'Self', 'Person', user=self.self_user)
        self.other = _employee('C-OT', 'Other', 'Emp')
        self.extra = _employee('C-XR', 'Extra', 'Out')
        _contract(self.inst_emp)
        _contract(self.wg_emp)
        _contract(self.mgr_emp)
        _contract(self.self_emp)
        _contract(self.other)
        self.wg_a.members.add(self.wg_emp, self.mgr_emp, self.self_emp, self.other)
        self.wg_b.members.add(self.extra)

        self.course = Course.objects.create(name='Lab', is_active=True)
        self.course.workgroups.add(self.wg_a)
        self.course.extra_employees.add(self.extra)
        CourseManager.objects.create(
            course=self.course, employee=self.mgr_emp, scope=CourseManager.Scope.WORKGROUP,
        )
        self.inactive = Course.objects.create(name='Old', is_active=False)
        self.inactive.workgroups.add(self.wg_a)
        CourseManager.objects.create(
            course=self.inactive, employee=self.mgr_emp, scope=CourseManager.Scope.INSTITUTE,
        )

    def test_institute_list_sees_extras_workgroup_list_does_not(self):
        inst_pks = set(visible_employees_for_course(self.inst_user, self.course).values_list('pk', flat=True))
        wg_pks = set(visible_employees_for_course(self.wg_user, self.course).values_list('pk', flat=True))
        self.assertIn(self.extra.pk, inst_pks)
        self.assertNotIn(self.extra.pk, wg_pks)
        self.assertIn(self.self_emp.pk, wg_pks)

    def test_workgroup_manager_write_scope(self):
        self.assertTrue(user_can_write_employee_course(self.mgr_user, self.course, self.self_emp))
        self.assertFalse(user_can_write_employee_course(self.mgr_user, self.course, self.extra))
        self.assertFalse(user_can_write_employee_course(self.wg_user, self.course, self.self_emp))
        self.assertTrue(user_can_write_employee_course(self.self_user, self.course, self.self_emp))
        self.assertFalse(user_can_write_employee_course(self.self_user, self.course, self.other))

    def test_institute_manager_sees_all_required(self):
        CourseManager.objects.filter(course=self.course, employee=self.mgr_emp).update(
            scope=CourseManager.Scope.INSTITUTE,
        )
        pks = set(visible_employees_for_course(self.mgr_user, self.course).values_list('pk', flat=True))
        self.assertIn(self.extra.pk, pks)
        self.assertTrue(user_can_write_employee_course(self.mgr_user, self.course, self.extra))

    def test_inactive_hidden_from_list_only_visible_to_manager(self):
        self.assertNotIn(self.inactive, list(visible_courses_for_user(self.inst_user)))
        self.assertIn(self.inactive, list(visible_courses_for_user(self.mgr_user)))
        self.assertIn(self.inactive, list(visible_courses_for_user(self.admin)))

    def test_list_user_sees_active_course_even_if_empty(self):
        empty = Course.objects.create(name='Empty', is_active=True)
        self.assertIn(empty, list(visible_courses_for_user(self.wg_user)))
        self.assertEqual(visible_employees_for_course(self.wg_user, empty).count(), 0)

    def test_hub_forbidden_without_access(self):
        self.assertFalse(user_can_access_hub(self.self_user))
        self.client.login(username='c-self', password='test')
        response = self.client.get(reverse('courses:hub'))
        self.assertEqual(response.status_code, 403)


class CourseRecordAndMediaTests(CoursesBase):
    def setUp(self):
        super().setUp()
        self.user = _ready('c-rec')
        self.emp = _employee('C-REC', 'Rec', 'Order', user=self.user)
        _contract(self.emp)
        self.course = Course.objects.create(
            name='First aid',
            evidence_type=Course.Evidence.CERTIFICATE,
        )
        self.course.extra_employees.add(self.emp)
        self.check_course = Course.objects.create(
            name='Briefing',
            evidence_type=Course.Evidence.CHECKBOX,
        )
        self.check_course.extra_employees.add(self.emp)

    def test_pdf_checkbox_future_and_replace(self):
        self.client.login(username='c-rec', password='test')
        url = reverse('courses:record', args=[self.course.pk])
        future = self.client.post(url, {
            'employee_id': str(self.emp.pk),
            'completed_on': (date.today() + timedelta(days=1)).isoformat(),
            'certificate': _pdf(),
            'next': '/courses/my/',
        })
        self.assertEqual(future.status_code, 302)
        self.assertEqual(CourseCompletion.objects.count(), 0)

        missing = self.client.post(url, {
            'employee_id': str(self.emp.pk),
            'completed_on': date.today().isoformat(),
            'next': '/courses/my/',
        })
        self.assertEqual(missing.status_code, 302)
        self.assertEqual(CourseCompletion.objects.count(), 0)

        first = self.client.post(url, {
            'employee_id': str(self.emp.pk),
            'completed_on': date.today().isoformat(),
            'certificate': _pdf('one.pdf'),
            'next': '/courses/my/',
        })
        self.assertEqual(first.status_code, 302)
        self.assertEqual(CourseCompletion.objects.filter(course=self.course).count(), 1)

        second = self.client.post(url, {
            'employee_id': str(self.emp.pk),
            'completed_on': date.today().isoformat(),
            'certificate': _pdf('two.pdf'),
            'next': '/courses/my/',
        })
        self.assertEqual(second.status_code, 302)
        self.assertEqual(CourseCompletion.objects.filter(course=self.course).count(), 2)

        check = self.client.post(reverse('courses:record', args=[self.check_course.pk]), {
            'employee_id': str(self.emp.pk),
            'completed_on': date.today().isoformat(),
            'next': '/courses/my/',
        })
        self.assertEqual(check.status_code, 302)
        row = CourseCompletion.objects.get(course=self.check_course)
        self.assertTrue(row.checked)
        self.assertFalse(row.certificate)

    def test_media_owner_ok_stranger_404(self):
        self.client.login(username='c-rec', password='test')
        self.client.post(reverse('courses:record', args=[self.course.pk]), {
            'employee_id': str(self.emp.pk),
            'completed_on': date.today().isoformat(),
            'certificate': _pdf(),
            'next': '/courses/my/',
        })
        completion = CourseCompletion.objects.get(course=self.course)
        media = reverse('core:stored_file', kwargs={'file_path': completion.certificate.name})
        own = self.client.get(media)
        self.assertEqual(own.status_code, 200)
        other = _ready('c-other')
        _employee('C-OTH', 'O', 'Ther', user=other)
        self.client.login(username='c-other', password='test')
        denied = self.client.get(media)
        self.assertEqual(denied.status_code, 404)


class CourseSettingsAndListTests(CoursesBase):
    def setUp(self):
        super().setUp()
        self.admin = _ready('c-sys', superuser=True)
        self.viewer = _ready('c-list')
        self.viewer.groups.add(Group.objects.get(name=GroupNames.COURSES_SEE_LISTS_INSTITUTE))
        self.emp = _employee('C-SET', 'Search', 'Unique', user=self.viewer)
        _contract(self.emp)
        self.other = _employee('C-ZZ', 'Other', 'Name')
        _contract(self.other)

    def test_settings_save_sanitize_managers_delete(self):
        self.client.login(username='c-sys', password='test')
        create = self.client.post(reverse('core_settings:global_settings'), {
            'action': 'save_courses',
            'name': 'Hygiene',
            'description': '<p>Keep clean</p><script>alert(1)</script>',
            'interval_months': '12',
            'evidence_type': Course.Evidence.CERTIFICATE,
            'warn_weeks': '4',
            'is_active': 'on',
            'all_institute': 'on',
            'manager_0_employee': str(self.emp.pk),
            'manager_0_scope': CourseManager.Scope.INSTITUTE,
        })
        self.assertEqual(create.status_code, 302)
        course = Course.objects.get(name='Hygiene')
        self.assertIn('Keep clean', course.description)
        self.assertNotIn('script', course.description.lower())
        link = CourseManager.objects.get(course=course)
        self.assertEqual(link.employee_id, self.emp.pk)
        self.assertEqual(link.scope, CourseManager.Scope.INSTITUTE)

        edit = self.client.get(reverse('core_settings:global_settings') + f'?tab=courses&edit={course.pk}')
        self.assertEqual(edit.status_code, 200)
        self.assertContains(edit, 'Hygiene')

        new = self.client.get(reverse('core_settings:global_settings') + '?tab=courses&new=1')
        self.assertEqual(new.status_code, 200)
        self.assertContains(new, 'New course')

        delete = self.client.post(reverse('core_settings:global_settings'), {
            'action': 'save_courses',
            'course_id': str(course.pk),
            'course_delete': '1',
        })
        self.assertEqual(delete.status_code, 302)
        self.assertFalse(Course.objects.filter(pk=course.pk).exists())

    def test_list_search_and_catalog_popup(self):
        course = Course.objects.create(name='Searchable', is_active=True, all_institute=True)
        self.client.login(username='c-list', password='test')
        url = reverse('courses:course_list', args=[course.pk])
        found = self.client.get(url, {'q': 'Unique'})
        self.assertEqual(found.status_code, 200)
        self.assertContains(found, 'Search Unique')
        missed = self.client.get(url, {'q': 'Nomatchxyz'})
        self.assertNotContains(missed, 'Search Unique')
        partial = self.client.get(url, {'q': 'Unique', 'partial': '1'})
        self.assertEqual(partial.status_code, 200)
        self.assertContains(partial, 'Search Unique')

        keys = {item['key'] for item in catalog_for_trigger('own_course_due')}
        self.assertIn('course_name', keys)
        self.assertIn('own_due_courses', keys)
        trigger_keys = {value for value, _label in LoginPopupConfig.TRIGGER_CHOICES}
        self.assertIn('own_course_due', trigger_keys)
        self.assertIn('managed_courses_due', trigger_keys)
        link_keys = {value for value, _label in LoginPopupConfig.LINK_CHOICES}
        self.assertIn('my_courses', link_keys)
        self.assertIn('course_lists', link_keys)

        LoginPopupConfig.objects.create(
            name='Course due',
            trigger='own_course_due',
            text='Please complete {{ course_name }}',
            enabled=True,
            show_popup=True,
        )
        popups = evaluate_login_popups(self.viewer, employee=self.emp)
        self.assertTrue(any('Searchable' in (p.get('text') or '') for p in popups))

    def test_my_courses_requires_employee(self):
        _ready('c-none')
        self.client.login(username='c-none', password='test')
        response = self.client.get(reverse('courses:my_courses'))
        self.assertEqual(response.status_code, 403)
