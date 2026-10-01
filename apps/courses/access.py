from django.db.models import Q

from apps.accounts.permissions import user_is_systemadmin
from apps.courses.models import Course, CourseCompletion, CourseManager
from apps.courses.services import is_required, required_employees
from apps.hr.models import Employee


def _employee(user):
    return getattr(user, 'employee', None) if user and user.is_authenticated else None


def _workgroup_ids(employee):
    if not employee:
        return set()
    return set(employee.workgroups.values_list('pk', flat=True))


def _is_admin(user):
    return bool(user and user.is_authenticated and user_is_systemadmin(user))


def user_can_view_institute_lists(user):
    if not user or not user.is_authenticated:
        return False
    if _is_admin(user):
        return True
    return user.has_perm('courses.view_institute_course_lists')


def user_can_view_workgroup_lists(user):
    if not user or not user.is_authenticated:
        return False
    if user_can_view_institute_lists(user):
        return True
    return user.has_perm('courses.view_workgroup_course_lists')


def user_manages_course(user, course) -> CourseManager | None:
    employee = _employee(user)
    if not employee:
        return None
    return CourseManager.objects.filter(course=course, employee=employee).first()


def user_manages_any_course(user) -> bool:
    employee = _employee(user)
    if not employee:
        return False
    return CourseManager.objects.filter(employee=employee).exists()


def user_can_access_hub(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if _is_admin(user):
        return True
    if user.has_perm('courses.view_institute_course_lists'):
        return True
    if user.has_perm('courses.view_workgroup_course_lists'):
        return True
    return user_manages_any_course(user)


def visible_courses_for_user(user):
    if not user_can_access_hub(user):
        return Course.objects.none()
    if _is_admin(user):
        return Course.objects.all()
    qs = Course.objects.filter(is_active=True)
    employee = _employee(user)
    if employee:
        managed_ids = CourseManager.objects.filter(employee=employee).values_list('course_id', flat=True)
        qs = Course.objects.filter(Q(pk__in=qs.values('pk')) | Q(pk__in=managed_ids))
    if user.has_perm('courses.view_institute_course_lists') or user.has_perm(
        'courses.view_workgroup_course_lists'
    ):
        return qs.distinct()
    if employee:
        return Course.objects.filter(
            pk__in=CourseManager.objects.filter(employee=employee).values('course_id')
        )
    return Course.objects.none()


def user_can_view_course(user, course) -> bool:
    if not course:
        return False
    return visible_courses_for_user(user).filter(pk=course.pk).exists()


def visible_employees_for_course(user, course):
    required = required_employees(course)
    if _is_admin(user) or user.has_perm('courses.view_institute_course_lists'):
        return required
    q = Q(pk__in=[])
    employee = _employee(user)
    wg_ids = _workgroup_ids(employee)
    if user.has_perm('courses.view_workgroup_course_lists') and wg_ids:
        q |= Q(workgroups__in=wg_ids)
    mgr = user_manages_course(user, course)
    if mgr:
        if mgr.scope == CourseManager.Scope.INSTITUTE:
            return required
        if wg_ids:
            q |= Q(workgroups__in=wg_ids)
    if q == Q(pk__in=[]):
        return Employee.objects.none()
    return required.filter(q).distinct()


def user_can_write_employee_course(user, course, subject) -> bool:
    if not user or not user.is_authenticated or not course or not subject:
        return False
    if _is_admin(user):
        return is_required(course, subject)
    employee = _employee(user)
    if employee and employee.pk == subject.pk:
        return bool(course.is_active and is_required(course, employee))
    mgr = user_manages_course(user, course)
    if not mgr:
        return False
    if not is_required(course, subject):
        return False
    if mgr.scope == CourseManager.Scope.INSTITUTE:
        return True
    return bool(_workgroup_ids(employee) & _workgroup_ids(subject))


def user_can_download_completion(user, completion: CourseCompletion) -> bool:
    if not completion:
        return False
    if _is_admin(user):
        return True
    employee = _employee(user)
    if employee and completion.employee_id == employee.pk:
        return True
    if not user_can_view_course(user, completion.course):
        return False
    return visible_employees_for_course(user, completion.course).filter(
        pk=completion.employee_id
    ).exists()


def attention_rows_visible_to_user(user, *, today=None):
    from apps.courses.services import annotate_employees

    if not user_can_access_hub(user):
        return []
    rows = []
    for course in visible_courses_for_user(user).filter(is_active=True):
        employees = list(
            visible_employees_for_course(user, course).order_by('last_name', 'first_name')
        )
        for row in annotate_employees(course, employees, today=today):
            if row['needs_attention']:
                rows.append(row)
    return rows


def courses_hub_needs_attention(user) -> bool:
    return bool(attention_rows_visible_to_user(user))
