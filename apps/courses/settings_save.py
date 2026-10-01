from __future__ import annotations

from apps.courses.forms import CourseForm
from apps.courses.models import Course, CourseManager
from apps.hr.models import Employee


class CourseSaveResult:
    def __init__(self, ok, *, message='', form=None, instance=None, manager_rows=None):
        self.ok = ok
        self.message = message
        self.form = form
        self.instance = instance
        self.manager_rows = manager_rows or []


def manager_rows_from_course(course):
    if course is None or not course.pk:
        return [{'employee_id': '', 'scope': CourseManager.Scope.WORKGROUP}]
    rows = [
        {'employee_id': str(link.employee_id), 'scope': link.scope}
        for link in course.manager_links.select_related('employee').order_by('pk')
    ]
    if not rows:
        rows = [{'employee_id': '', 'scope': CourseManager.Scope.WORKGROUP}]
    return rows


def manager_rows_from_post(post):
    rows = []
    for index in range(80):
        emp_key = f'manager_{index}_employee'
        scope_key = f'manager_{index}_scope'
        if emp_key not in post and scope_key not in post:
            continue
        employee_id = (post.get(emp_key) or '').strip()
        scope = (post.get(scope_key) or CourseManager.Scope.WORKGROUP).strip()
        if scope not in CourseManager.Scope.values:
            scope = CourseManager.Scope.WORKGROUP
        rows.append({'employee_id': employee_id, 'scope': scope})
    if not rows:
        rows = [{'employee_id': '', 'scope': CourseManager.Scope.WORKGROUP}]
    return rows


def _save_managers(course, rows):
    CourseManager.objects.filter(course=course).delete()
    seen = set()
    for row in rows:
        raw = (row.get('employee_id') or '').strip()
        if not raw:
            continue
        try:
            employee_id = int(raw)
        except (TypeError, ValueError):
            continue
        if employee_id in seen:
            continue
        if not Employee.objects.filter(pk=employee_id).exists():
            continue
        scope = row.get('scope') or CourseManager.Scope.WORKGROUP
        if scope not in CourseManager.Scope.values:
            scope = CourseManager.Scope.WORKGROUP
        CourseManager.objects.create(course=course, employee_id=employee_id, scope=scope)
        seen.add(employee_id)


def save_courses_from_post(request) -> CourseSaveResult:
    post = request.POST
    if post.get('course_delete') and post.get('course_id'):
        deleted, _ = Course.objects.filter(pk=post.get('course_id')).delete()
        if deleted:
            return CourseSaveResult(True, message='Course deleted.')
        return CourseSaveResult(False, message='Course not found.')

    instance = None
    pk = (post.get('course_id') or '').strip()
    if pk:
        instance = Course.objects.filter(pk=pk).first()
        if instance is None:
            return CourseSaveResult(False, message='Course not found.')

    form = CourseForm(post, instance=instance)
    manager_rows = manager_rows_from_post(post)
    if not form.is_valid():
        return CourseSaveResult(
            False,
            form=form,
            instance=instance,
            manager_rows=manager_rows,
        )
    course = form.save()
    _save_managers(course, manager_rows)
    return CourseSaveResult(
        True,
        message='Course saved.',
        instance=course,
        manager_rows=manager_rows_from_course(course),
    )
