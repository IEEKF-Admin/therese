import calendar
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.holidays.access import (
    pending_requests_for_approver,
    user_can_approve_all,
    user_can_approve_workgroup,
)
from apps.holidays.features import holiday_flags
from apps.holidays.forms import HolidayEntitlementForm, HolidayProfileForm, save_entitlements
from apps.holidays.models import HolidayRequest
from apps.holidays.services import (
    classify_dates,
    create_request,
    decide_requests,
    delete_request,
    entitlement_days,
    get_or_create_profile,
    gantt_bars,
    gantt_employees,
    remaining_days,
    suggested_entitlement,
    used_days,
)
from apps.hr.models import Workgroup


def _require_employee(request):
    employee = getattr(request.user, 'employee', None)
    if employee is None:
        raise PermissionDenied('No employee profile.')
    return employee


def _require_planning(request):
    if not holiday_flags()['planning']:
        raise PermissionDenied('Holiday planning is disabled.')


@login_required
def my_holidays(request):
    _require_planning(request)
    employee = _require_employee(request)
    profile = get_or_create_profile(employee)
    today = date.today()
    year = today.year
    try:
        view_year = int(request.GET.get('year', year))
        view_month = int(request.GET.get('month', today.month))
    except (TypeError, ValueError):
        view_year, view_month = year, today.month
    if view_month < 1 or view_month > 12:
        view_month = today.month

    if request.method == 'POST' and request.POST.get('action') == 'save_profile':
        form = HolidayProfileForm(request.POST, request.FILES, instance=profile)
        ent_form = HolidayEntitlementForm(request.POST)
        if form.is_valid() and ent_form.is_valid():
            form.save()
            save_entitlements(
                employee,
                ent_form.cleaned_data['this_year'],
                ent_form.cleaned_data['next_year'],
            )
            messages.success(request, 'Holiday settings were saved.')
            return redirect('holidays:my_holidays')
    else:
        this_val = entitlement_days(employee, year)
        next_val = entitlement_days(employee, year + 1)
        form = HolidayProfileForm(instance=profile)
        ent_form = HolidayEntitlementForm(initial={
            'this_year': this_val,
            'next_year': next_val,
        })

    month_start = date(view_year, view_month, 1)
    if view_month == 12:
        month_end = date(view_year, 12, 31)
    else:
        month_end = date(view_year, view_month + 1, 1) - timedelta(days=1)
    rows, _counted = classify_dates(employee, month_start, month_end)
    by_date = {row['date']: row for row in rows}
    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdatescalendar(view_year, view_month):
        weeks.append([
            {
                'date': day,
                'in_month': day.month == view_month,
                'info': by_date.get(day),
            }
            for day in week
        ])

    prev_month = month_start - timedelta(days=1)
    next_month = month_end + timedelta(days=1)
    requests = HolidayRequest.objects.filter(employee=employee).order_by('-start_date')

    return render(request, 'holidays/my_holidays.html', {
        'profile_form': form,
        'entitlement_form': ent_form,
        'weeks': weeks,
        'view_year': view_year,
        'view_month': view_month,
        'month_label': month_start.strftime('%B %Y'),
        'prev_year': prev_month.year,
        'prev_month': prev_month.month,
        'next_year': next_month.year,
        'next_month': next_month.month,
        'remaining_this': remaining_days(employee, year),
        'remaining_next': remaining_days(employee, year + 1),
        'used_this': used_days(employee, year),
        'entitlement_this': entitlement_days(employee, year),
        'suggested_this': suggested_entitlement(employee, year),
        'requests': requests,
        'approval_enabled': holiday_flags()['approval'],
        'gantt_enabled': holiday_flags()['gantt'],
    })


@login_required
@require_POST
def create_holiday_request(request):
    _require_planning(request)
    employee = _require_employee(request)
    raw = request.POST.getlist('dates') or (request.POST.get('dates') or '').split(',')
    dates = []
    for item in raw:
        item = (item or '').strip()
        if not item:
            continue
        try:
            dates.append(date.fromisoformat(item))
        except ValueError:
            messages.error(request, f'Invalid date: {item}')
            return redirect('holidays:my_holidays')
    try:
        created = create_request(
            request.user, employee, dates, comment=request.POST.get('comment', ''),
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))
        return redirect('holidays:my_holidays')
    messages.success(
        request,
        f'Holiday request saved ({created.day_count} day(s) from {created.start_date:%d.%m.%Y} to {created.end_date:%d.%m.%Y}).',
    )
    return redirect('holidays:my_holidays')


@login_required
@require_POST
def delete_holiday_request(request, pk):
    _require_planning(request)
    holiday_request = get_object_or_404(HolidayRequest, pk=pk)
    try:
        delete_request(request.user, holiday_request)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))
        return redirect('holidays:my_holidays')
    messages.success(request, 'Holiday request deleted.')
    return redirect('holidays:my_holidays')


@login_required
def request_pdf(request, pk):
    _require_planning(request)
    holiday_request = get_object_or_404(HolidayRequest, pk=pk)
    employee = getattr(request.user, 'employee', None)
    from apps.holidays.access import user_can_approve_request
    if holiday_request.employee_id != getattr(employee, 'pk', None) and not user_can_approve_request(
        request.user, holiday_request,
    ) and not user_can_approve_all(request.user):
        raise PermissionDenied
    if holiday_request.pdf_file:
        holiday_request.pdf_file.open('rb')
        return FileResponse(
            holiday_request.pdf_file,
            content_type='application/pdf',
            filename=f'holiday-{holiday_request.pk}.pdf',
        )
    from apps.holidays.pdf import render_request_pdf
    content = render_request_pdf(holiday_request, signed=False)
    response = HttpResponse(content, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="holiday-{holiday_request.pk}.pdf"'
    return response


@login_required
def approve_list(request):
    if not holiday_flags()['approval']:
        raise PermissionDenied('Holiday approval is disabled.')
    if not user_can_approve_workgroup(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        ids = request.POST.getlist('request_id')
        action = request.POST.get('action')
        qs = pending_requests_for_approver(request.user).filter(pk__in=ids)
        approve = action == 'approve'
        if action in ('approve', 'reject'):
            updated = decide_requests(
                request.user, qs, approve=approve,
                comment=request.POST.get('rejection_comment', ''),
            )
            messages.success(
                request,
                f'{len(updated)} request(s) {"approved" if approve else "rejected"}.',
            )
        return redirect('holidays:approve_list')

    pending = list(
        pending_requests_for_approver(request.user).order_by('start_date', 'employee__last_name')
    )
    viewer = getattr(request.user, 'employee', None)
    wg_ids = set(viewer.workgroups.values_list('pk', flat=True)) if viewer else set()
    in_wg, out_wg = [], []
    for item in pending:
        subject_wgs = set(item.employee.workgroups.values_list('pk', flat=True))
        if wg_ids & subject_wgs:
            in_wg.append(item)
        else:
            out_wg.append(item)
    return render(request, 'holidays/approve_list.html', {
        'in_workgroup': in_wg,
        'out_workgroup': out_wg,
        'is_super_approver': user_can_approve_all(request.user),
    })


@login_required
def gantt(request):
    if not holiday_flags()['gantt']:
        raise PermissionDenied('The holiday overview is disabled.')
    _require_employee(request)
    today = date.today()
    try:
        year = int(request.GET.get('year', today.year))
    except (TypeError, ValueError):
        year = today.year
    workgroup_id = request.GET.get('workgroup') or ''
    institute = request.GET.get('scope') == 'institute'
    selected_wg = None
    if workgroup_id and not institute:
        try:
            selected_wg = int(workgroup_id)
        except (TypeError, ValueError):
            selected_wg = None
    employees = list(gantt_employees(
        request.user, workgroup_id=selected_wg, institute=institute,
    ))
    rows, year_days = gantt_bars(employees, year)
    workgroups = Workgroup.objects.order_by('short_name')
    return render(request, 'holidays/gantt.html', {
        'rows': rows,
        'year': year,
        'year_days': year_days,
        'workgroups': workgroups,
        'selected_workgroup': selected_wg,
        'institute': institute,
        'months': [
            date(year, month, 1) for month in range(1, 13)
        ],
    })
