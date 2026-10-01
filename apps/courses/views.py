from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.courses.access import (
    user_can_access_hub,
    user_can_view_course,
    user_can_write_employee_course,
    visible_courses_for_user,
    visible_employees_for_course,
)
from apps.courses.forms import CompletionForm
from apps.courses.models import Course
from apps.courses.services import (
    STATUS_DUE,
    STATUS_OK,
    STATUS_WARN,
    annotate_employees,
    courses_required_for,
    record_completion,
)
from apps.hr.employee_list_helpers import employee_list_search_q
from apps.hr.models import Employee


def _require_employee(request):
    employee = getattr(request.user, 'employee', None)
    if employee is None:
        raise PermissionDenied('No employee profile.')
    return employee


@login_required
def my_courses(request):
    employee = _require_employee(request)
    today = date.today()
    courses = list(courses_required_for(employee, active_only=True, as_of=today))
    rows = [annotate_employees(course, [employee], today=today)[0] for course in courses]
    for row in rows:
        row['can_write'] = user_can_write_employee_course(request.user, row['course'], employee)
    return render(request, 'courses/my.html', {
        'rows': rows,
        'today': today,
        'today_iso': today.isoformat(),
    })


@login_required
def hub(request):
    if not user_can_access_hub(request.user):
        raise PermissionDenied
    today = date.today()
    cards = []
    for course in visible_courses_for_user(request.user).order_by('name'):
        employees = list(
            visible_employees_for_course(request.user, course).order_by('last_name', 'first_name')
        )
        annotated = annotate_employees(course, employees, today=today)
        counts = {STATUS_OK: 0, STATUS_WARN: 0, STATUS_DUE: 0}
        for row in annotated:
            counts[row['status']] += 1
        cards.append({
            'course': course,
            'counts': counts,
            'total': len(annotated),
        })
    return render(request, 'courses/hub.html', {'cards': cards})


def _status_filter(rows, status):
    if status in (STATUS_OK, STATUS_WARN, STATUS_DUE):
        return [row for row in rows if row['status'] == status]
    return rows


@login_required
def course_list(request, pk):
    if not user_can_access_hub(request.user):
        raise PermissionDenied
    course = get_object_or_404(Course, pk=pk)
    if not user_can_view_course(request.user, course):
        raise PermissionDenied
    today = date.today()
    search_query = request.GET.get('q', '').strip()
    status = (request.GET.get('status') or '').strip()
    employees = visible_employees_for_course(request.user, course).order_by(
        'last_name', 'first_name',
    )
    if search_query:
        employees = employees.filter(employee_list_search_q(search_query, as_of=today)).distinct()
    employees = list(employees)
    rows = annotate_employees(course, employees, today=today)
    for row in rows:
        row['can_write'] = user_can_write_employee_course(request.user, course, row['employee'])
    rows = _status_filter(rows, status)
    context = {
        'course': course,
        'rows': rows,
        'search_query': search_query,
        'status_filter': status,
        'today': today,
        'today_iso': today.isoformat(),
        'can_write_any': any(row['can_write'] for row in rows),
    }
    if request.GET.get('partial') == '1':
        return render(request, 'courses/_course_list_body.html', context)
    return render(request, 'courses/course_list.html', context)


@login_required
@require_POST
def record(request, pk):
    course = get_object_or_404(Course, pk=pk)
    form = CompletionForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Please correct the completion form.')
        return _redirect_after_record(request, course)
    employee_id = form.cleaned_data.get('employee_id')
    if employee_id:
        employee = get_object_or_404(Employee, pk=employee_id)
    else:
        employee = getattr(request.user, 'employee', None)
        if employee is None:
            raise PermissionDenied('No employee profile.')
    if not user_can_write_employee_course(request.user, course, employee):
        raise PermissionDenied
    try:
        record_completion(
            course,
            employee,
            actor=request.user,
            completed_on=form.cleaned_data['completed_on'],
            certificate=form.cleaned_data.get('certificate'),
        )
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))
        return _redirect_after_record(request, course)
    messages.success(request, f'Recorded {course.name} for {employee.get_full_name()}.')
    return _redirect_after_record(request, course)


def _redirect_after_record(request, course):
    nxt = (request.POST.get('next') or '').strip()
    if nxt.startswith('/'):
        return redirect(nxt)
    if user_can_view_course(request.user, course):
        return redirect('courses:course_list', pk=course.pk)
    return redirect('courses:my_courses')
