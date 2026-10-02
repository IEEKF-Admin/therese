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


def calendar_year_period(completed_on: date, years: int) -> tuple[date, date]:
    """Return (period_end, next_due) for a calendar-year interval.

    A completion in year Y covers through 31 December of Y + years − 1.
    Next due is 1 January of Y + years.
    """
    if years < 1:
        raise ValueError('years must be >= 1')
    period_end = date(completed_on.year + years - 1, 12, 31)
    next_due = date(completed_on.year + years, 1, 1)
    return period_end, next_due


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


def earliest_date_map(courses, employees):
    ids = [emp.pk for emp in employees]
    if not ids or not courses:
        return {}
    rows = (
        CourseCompletion.objects.filter(course__in=courses, employee_id__in=ids)
        .order_by('employee_id', 'completed_on', 'pk')
    )
    found = {}
    for row in rows:
        if row.employee_id not in found:
            found[row.employee_id] = row.completed_on
    return found


def _status_and_due(course, last, today, *, first_target_on=None, deferred_substitute=False):
    if last is None and deferred_substitute:
        if first_target_on is None:
            return STATUS_OK, None
        last = date(first_target_on.year - 1, 12, 31)
    if last is None:
        return STATUS_DUE, None
    if course.interval_years:
        period_end, next_due = calendar_year_period(last, course.interval_years)
        if today >= next_due:
            return STATUS_DUE, next_due
        if course.warn_weeks and today >= period_end - timedelta(weeks=course.warn_weeks):
            return STATUS_WARN, next_due
        return STATUS_OK, next_due
    if course.interval_months:
        next_due = add_calendar_months(last, course.interval_months)
        if today >= next_due:
            return STATUS_DUE, next_due
        if course.warn_weeks and today >= next_due - timedelta(weeks=course.warn_weeks):
            return STATUS_WARN, next_due
        return STATUS_OK, next_due
    return STATUS_OK, None


def _status_row(course, employee, *, status, last_completed, due_date, completion, covered_by=None):
    return {
        'course': course,
        'employee': employee,
        'status': status,
        'label': STATUS_LABELS[status],
        'last_completed': last_completed,
        'due_date': due_date,
        'completion': completion,
        'covered_by': covered_by,
        'needs_attention': status in (STATUS_WARN, STATUS_DUE),
    }


def completion_status(course, employee, *, today=None, completion=None) -> dict:
    today = today or date.today()
    return annotate_employees(course, [employee], today=today)[0]


def annotate_employees(course, employees, *, today=None):
    today = today or date.today()
    employees = list(employees)
    latest = latest_completions_map(course, employees)
    targets = list(course.substitutes_for.all()) if getattr(course, 'pk', None) else []
    substituters = (
        list(course.substituted_by.prefetch_related('substitutes_for').all())
        if getattr(course, 'pk', None)
        else []
    )
    deferred = bool(course.interval_years) and bool(targets)
    covering_maps = {item.pk: latest_completions_map(item, employees) for item in substituters}
    sub_targets = {item.pk: list(item.substitutes_for.all()) for item in substituters}
    earliest_target = earliest_date_map(targets, employees) if deferred else {}
    earliest_for_sub = {
        item.pk: earliest_date_map(sub_targets[item.pk], employees)
        for item in substituters
    }
    rows = []
    for employee in employees:
        own = latest.get(employee.pk)
        last_own = own.completed_on if own else None
        covering_last = last_own
        covering_from = None
        for item in substituters:
            sub = covering_maps[item.pk].get(employee.pk)
            if sub is not None and (covering_last is None or sub.completed_on >= covering_last):
                covering_last = sub.completed_on
                covering_from = item
        last_for_interval = last_own if deferred else covering_last
        first_target_on = earliest_target.get(employee.pk) if deferred else None
        status, next_due = _status_and_due(
            course,
            last_for_interval,
            today,
            first_target_on=first_target_on,
            deferred_substitute=deferred,
        )
        covered_by = covering_from if status != STATUS_DUE and covering_from is not None else None
        if substituters:
            for item in substituters:
                sub = covering_maps[item.pk].get(employee.pk)
                sub_last = sub.completed_on if sub else None
                sub_deferred = bool(item.interval_years) and bool(sub_targets[item.pk])
                sub_status, _sub_due = _status_and_due(
                    item,
                    sub_last,
                    today,
                    first_target_on=earliest_for_sub[item.pk].get(employee.pk),
                    deferred_substitute=sub_deferred,
                )
                if sub_status == STATUS_DUE:
                    status = STATUS_OK
                    next_due = None
                    covered_by = item
                    break
        if deferred:
            covered_by = None
        rows.append(
            _status_row(
                course,
                employee,
                status=status,
                last_completed=last_own,
                due_date=next_due,
                completion=own,
                covered_by=covered_by,
            )
        )
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
