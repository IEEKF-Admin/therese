from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.core.upload_validation import PDF_EXT, validate_upload
from apps.courses.models import Course, CourseCompletion
from apps.hr.models import Employee


STATUS_OK = 'ok'
STATUS_WARN = 'warn'
STATUS_DUE = 'due'

STATUS_LABELS = {
    STATUS_OK: 'Current',
    STATUS_WARN: 'Due soon',
    STATUS_DUE: 'Due',
}


def add_calendar_months(start: date, months: int) -> date:
    """Add whole calendar months; clamp day to last day of target month."""
    if months < 0:
        raise ValueError('months must be >= 0')
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def current_contract_q(as_of: date | None = None) -> Q:
    as_of = as_of or date.today()
    return (
        Q(contracts__is_active=True)
        & Q(contracts__valid_from__lte=as_of)
        & (Q(contracts__valid_until__isnull=True) | Q(contracts__valid_until__gte=as_of))
    )


def is_institute_member(employee, as_of: date | None = None) -> bool:
    if employee is None or employee.is_external:
        return False
    return Employee.objects.filter(pk=employee.pk).filter(current_contract_q(as_of)).exists()


def required_employees(course, as_of: date | None = None):
    """Employees required to take this course (no assignment rows)."""
    as_of = as_of or date.today()
    ids = set()
    if course.all_institute:
        ids.update(
            Employee.objects.visible()
            .filter(is_external=False)
            .filter(current_contract_q(as_of))
            .values_list('pk', flat=True)
        )
    wg_ids = list(course.workgroups.values_list('pk', flat=True))
    if wg_ids:
        ids.update(
            Employee.objects.visible()
            .filter(workgroups__in=wg_ids)
            .values_list('pk', flat=True)
        )
    ids.update(course.extra_employees.values_list('pk', flat=True))
    if not ids:
        return Employee.objects.none()
    return Employee.objects.visible().filter(pk__in=ids).distinct()


def is_required(course, employee, as_of: date | None = None) -> bool:
    if employee is None:
        return False
    return required_employees(course, as_of=as_of).filter(pk=employee.pk).exists()


def courses_required_for(employee, *, active_only=True, as_of: date | None = None):
    if employee is None:
        return Course.objects.none()
    as_of = as_of or date.today()
    wg_ids = list(employee.workgroups.values_list('pk', flat=True))
    q = Q(extra_employees=employee)
    if wg_ids:
        q |= Q(workgroups__in=wg_ids)
    if is_institute_member(employee, as_of=as_of):
        q |= Q(all_institute=True)
    qs = Course.objects.filter(q).distinct()
    if active_only:
        qs = qs.filter(is_active=True)
    return qs


def latest_completion(course, employee) -> CourseCompletion | None:
    if employee is None:
        return None
    return (
        CourseCompletion.objects.filter(course=course, employee=employee)
        .order_by('-completed_on', '-pk')
        .first()
    )


def latest_completions_map(course, employees):
    ids = [emp.pk for emp in employees]
    if not ids:
        return {}
    rows = (
        CourseCompletion.objects.filter(course=course, employee_id__in=ids)
        .order_by('employee_id', '-completed_on', '-pk')
    )
    found = {}
    for row in rows:
        if row.employee_id not in found:
            found[row.employee_id] = row
    return found


def completion_status(course, employee, *, today=None, completion=None) -> dict:
    today = today or date.today()
    if completion is None:
        completion = latest_completion(course, employee)
    last = completion.completed_on if completion else None
    next_due = None
    if last is None:
        status = STATUS_DUE
    elif not course.interval_months:
        status = STATUS_OK
    else:
        next_due = add_calendar_months(last, course.interval_months)
        if today >= next_due:
            status = STATUS_DUE
        elif course.warn_weeks and today >= next_due - timedelta(weeks=course.warn_weeks):
            status = STATUS_WARN
        else:
            status = STATUS_OK
    return {
        'course': course,
        'employee': employee,
        'status': status,
        'label': STATUS_LABELS[status],
        'last_completed': last,
        'due_date': next_due,
        'completion': completion,
        'needs_attention': status in (STATUS_WARN, STATUS_DUE),
    }


def annotate_employees(course, employees, *, today=None):
    today = today or date.today()
    latest = latest_completions_map(course, employees)
    rows = []
    for employee in employees:
        row = completion_status(
            course, employee, today=today, completion=latest.get(employee.pk),
        )
        rows.append(row)
    return rows


def attention_rows_for_employee(employee, *, today=None):
    today = today or date.today()
    rows = []
    for course in courses_required_for(employee, active_only=True, as_of=today):
        row = completion_status(course, employee, today=today)
        if row['needs_attention']:
            rows.append(row)
    return rows


def my_courses_needs_attention(user) -> bool:
    employee = getattr(user, 'employee', None) if user and getattr(user, 'is_authenticated', False) else None
    if employee is None:
        return False
    return bool(attention_rows_for_employee(employee))


def attention_reference_key(row, *, managed=False) -> str:
    course = row['course']
    employee = row['employee']
    status = row['status']
    due = row['due_date']
    due_s = due.isoformat() if due else 'none'
    if managed:
        return f'course_managed:{employee.pk}:{course.pk}:{status}:{due_s}'
    return f'course_own:{course.pk}:{status}:{due_s}'


def record_completion(course, employee, *, actor, completed_on, certificate=None):
    if completed_on is None:
        raise ValidationError('Completed on is required.')
    if completed_on > date.today():
        raise ValidationError('Date cannot be in the future.')
    checked = False
    saved_file = None
    if course.evidence_type == Course.Evidence.CERTIFICATE:
        if not certificate:
            raise ValidationError('Certificate PDF is required.')
        validate_upload(certificate, allowed_extensions=PDF_EXT)
        saved_file = certificate
    else:
        checked = True
    return CourseCompletion.objects.create(
        course=course,
        employee=employee,
        completed_on=completed_on,
        checked=checked,
        certificate=saved_file or '',
        recorded_by=actor if getattr(actor, 'is_authenticated', False) else None,
    )
