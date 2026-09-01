"""Holiday calculation and request lifecycle."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.holidays.entitlement import DEFAULT_RATES, months_to_index
from apps.holidays.features import holiday_flags
from apps.holidays.models import (
    HolidayCustomDay,
    HolidayEntitlementRate,
    HolidayProfile,
    HolidayRequest,
    HolidayYearEntitlement,
)
from apps.holidays.public_holidays import public_holidays_for_year
from apps.hr.validity import contract_open_on_q, resolve_as_of


CONSUMING_STATUSES = (HolidayRequest.Status.PENDING, HolidayRequest.Status.APPROVED)


def get_or_create_profile(employee):
    profile, _ = HolidayProfile.objects.get_or_create(employee=employee)
    return profile


def active_contract_on(employee, when):
    return employee.contracts.filter(contract_open_on_q(when), is_active=True).first()


def contract_months_in_year(employee, year):
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    contracts = employee.contracts.filter(is_active=True)
    months = set()
    for contract in contracts:
        start = max(contract.valid_from, year_start)
        end = contract.valid_until or year_end
        end = min(end, year_end)
        if end < start:
            continue
        cursor = date(start.year, start.month, 1)
        last = date(end.year, end.month, 1)
        while cursor <= last:
            months.add(cursor.month)
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
    return len(months)


def suggested_entitlement(employee, year):
    profile = get_or_create_profile(employee)
    weekdays = profile.workdays_per_week() or 5
    months = contract_months_in_year(employee, year)
    if months <= 0:
        return Decimal('0')
    rate = HolidayEntitlementRate.objects.filter(
        weekdays=weekdays, contract_months=months,
    ).first()
    if rate:
        value = rate.days
    else:
        row = DEFAULT_RATES.get(weekdays) or DEFAULT_RATES[5]
        value = row[months_to_index(months)]
    return apply_half_day_rounding(value)


def apply_half_day_rounding(value):
    from apps.core.models import GlobalSetting

    setting = GlobalSetting.get_solo()
    mode = getattr(setting, 'holiday_half_day_rounding', 'up') or 'up'
    quant = Decimal('1')
    if value == value.to_integral_value():
        return value.quantize(quant)
    if mode == 'down':
        return value.to_integral_value(rounding=ROUND_FLOOR)
    return value.to_integral_value(rounding=ROUND_CEILING)


def entitlement_days(employee, year):
    row = HolidayYearEntitlement.objects.filter(employee=employee, year=year).first()
    if row:
        return row.days
    return Decimal('0')


def used_days(employee, year, *, exclude_pk=None):
    qs = HolidayRequest.objects.filter(
        employee=employee,
        status__in=CONSUMING_STATUSES,
        start_date__year=year,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    total = Decimal('0')
    for request in qs:
        for raw in request.counted_dates or []:
            day = date.fromisoformat(raw) if isinstance(raw, str) else raw
            if day.year == year:
                total += Decimal('1')
        if request.start_date.year != year and request.end_date.year == year:
            continue
    # Requests spanning years: count dates already handled via counted_dates.
    extra = HolidayRequest.objects.filter(
        employee=employee,
        status__in=CONSUMING_STATUSES,
        start_date__year__lt=year,
        end_date__year__gte=year,
    )
    if exclude_pk:
        extra = extra.exclude(pk=exclude_pk)
    for request in extra:
        for raw in request.counted_dates or []:
            day = date.fromisoformat(raw) if isinstance(raw, str) else raw
            if day.year == year:
                total += Decimal('1')
    return total


def remaining_days(employee, year, *, exclude_pk=None):
    return entitlement_days(employee, year) - used_days(employee, year, exclude_pk=exclude_pk)


def _state_code():
    from apps.core.models import GlobalSetting
    return getattr(GlobalSetting.get_solo(), 'holiday_federal_state', '') or ''


def public_holiday_map(year):
    return public_holidays_for_year(year, _state_code())


def custom_days_for_years(years):
    return list(HolidayCustomDay.objects.filter(year__in=set(years)))


def _employee_vacation_date_set(employee, *, exclude_pk=None):
    qs = HolidayRequest.objects.filter(
        employee=employee,
        status__in=CONSUMING_STATUSES,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    dates = set()
    for request in qs:
        for raw in request.counted_dates or []:
            dates.add(date.fromisoformat(raw) if isinstance(raw, str) else raw)
    return dates


def _previous_workday(day, profile, holiday_dates):
    cursor = day - timedelta(days=1)
    for _ in range(14):
        if profile.works_on_weekday(cursor.weekday()) and cursor not in holiday_dates:
            return cursor
        cursor -= timedelta(days=1)
    return day - timedelta(days=1)


def _next_workday(day, profile, holiday_dates):
    cursor = day + timedelta(days=1)
    for _ in range(14):
        if profile.works_on_weekday(cursor.weekday()) and cursor not in holiday_dates:
            return cursor
        cursor += timedelta(days=1)
    return day + timedelta(days=1)


def classify_dates(employee, start, end, *, extra_selected=None, exclude_pk=None):
    """Classify each calendar day in [start, end]."""
    profile = get_or_create_profile(employee)
    years = list(range(start.year, end.year + 1))
    public = {}
    for year in years:
        public.update(public_holiday_map(year))
    custom = custom_days_for_years(years)
    custom_by_date = {item.day: item for item in custom}
    always_holiday = set(public.keys()) | {
        item.day for item in custom if item.mode == HolidayCustomDay.Mode.ALWAYS
    }
    selected = set()
    cursor = start
    while cursor <= end:
        selected.add(cursor)
        cursor += timedelta(days=1)
    if extra_selected:
        selected |= set(extra_selected)

    other_vacation = _employee_vacation_date_set(employee, exclude_pk=exclude_pk)
    proposed_vacation = set()

    rows = []
    cursor = start
    while cursor <= end:
        is_weekend = cursor.weekday() >= 5
        is_workday = profile.works_on_weekday(cursor.weekday())
        public_name = public.get(cursor)
        custom_item = custom_by_date.get(cursor)
        label = public_name or (custom_item.name if custom_item else '')
        rows.append({
            'date': cursor,
            'is_weekend': is_weekend,
            'is_workday': is_workday,
            'public_name': public_name,
            'custom': custom_item,
            'label': label,
            'counts': False,
            'kind': 'other',
        })
        cursor += timedelta(days=1)

    # First pass: obvious holidays and workdays (custom AND/OR resolved second)
    for row in rows:
        day = row['date']
        if not row['is_workday']:
            row['kind'] = 'off'
            continue
        if day in public:
            row['kind'] = 'public'
            continue
        custom_item = row['custom']
        if custom_item and custom_item.mode == HolidayCustomDay.Mode.ALWAYS:
            row['kind'] = 'custom'
            continue
        if custom_item:
            row['kind'] = 'custom_pending'
            continue
        row['kind'] = 'work'
        if day in selected:
            row['counts'] = True
            proposed_vacation.add(day)

    vacation_set = other_vacation | proposed_vacation | {
        row['date'] for row in rows if row['counts']
    }

    for row in rows:
        if row['kind'] != 'custom_pending':
            continue
        custom_item = row['custom']
        prev_d = _previous_workday(row['date'], profile, always_holiday)
        next_d = _next_workday(row['date'], profile, always_holiday)
        before = prev_d in vacation_set or prev_d in selected
        after = next_d in vacation_set or next_d in selected
        if custom_item.mode == HolidayCustomDay.Mode.EXCEPT_AND:
            is_holiday = not (before and after)
        else:
            is_holiday = not (before or after)
        if is_holiday:
            row['kind'] = 'custom'
            row['counts'] = False
        else:
            row['kind'] = 'work'
            if row['date'] in selected:
                row['counts'] = True

    counted = [row['date'] for row in rows if row['counts']]
    return rows, counted


def parse_iso_dates(raw_list):
    dates = []
    for raw in raw_list:
        if not raw:
            continue
        dates.append(date.fromisoformat(raw) if isinstance(raw, str) else raw)
    return sorted(set(dates))


def create_request(user, employee, dates, *, comment=''):
    flags = holiday_flags()
    if not flags['planning']:
        raise ValidationError('Holiday planning is disabled.')
    if getattr(employee, 'is_external', False):
        raise ValidationError('Holiday planning is only available for institute employees.')
    if not dates:
        raise ValidationError('Select at least one day.')
    dates = sorted(set(dates))
    start, end = dates[0], dates[-1]
    as_of = resolve_as_of(None)
    if not active_contract_on(employee, as_of):
        raise ValidationError('An active contract is required to request leave.')

    _rows, counted = classify_dates(employee, start, end, extra_selected=dates)
    counted = [day for day in counted if day in set(dates)]
    if not counted:
        raise ValidationError('None of the selected days count as vacation days.')

    overlap = _employee_vacation_date_set(employee)
    if overlap & set(counted):
        raise ValidationError('This leave overlaps an existing request.')

    by_year = {}
    for day in counted:
        by_year.setdefault(day.year, 0)
        by_year[day.year] += 1
    for year, n in by_year.items():
        remaining = remaining_days(employee, year)
        if Decimal(n) > remaining:
            raise ValidationError(
                f'Not enough remaining days in {year} ({remaining} left, {n} requested).'
            )

    status = (
        HolidayRequest.Status.PENDING
        if flags['approval']
        else HolidayRequest.Status.APPROVED
    )
    request = HolidayRequest.objects.create(
        employee=employee,
        start_date=start,
        end_date=end,
        day_count=Decimal(len(counted)),
        counted_dates=[day.isoformat() for day in counted],
        status=status,
        comment=comment or '',
        submitted_at=timezone.now(),
        decided_at=None if flags['approval'] else timezone.now(),
        decided_by=None if flags['approval'] else user,
    )
    if not flags['approval']:
        attach_pdf(request, signed=False)
    return request


def delete_request(user, request):
    flags = holiday_flags()
    employee = getattr(user, 'employee', None)
    if not employee or request.employee_id != employee.pk:
        raise ValidationError('You can only delete your own requests.')
    if flags['approval'] and request.status != HolidayRequest.Status.PENDING:
        raise ValidationError('Approved or rejected requests cannot be deleted.')
    if request.pdf_file:
        request.pdf_file.delete(save=False)
    request.delete()


def decide_requests(user, queryset, *, approve, comment=''):
    flags = holiday_flags()
    if not flags['approval']:
        raise ValidationError('Holiday approval is disabled.')
    from apps.holidays.access import user_can_approve_request

    updated = []
    for request in queryset:
        if request.status != HolidayRequest.Status.PENDING:
            continue
        if not user_can_approve_request(user, request):
            continue
        request.status = (
            HolidayRequest.Status.APPROVED if approve else HolidayRequest.Status.REJECTED
        )
        request.decided_at = timezone.now()
        request.decided_by = user
        if not approve:
            request.rejection_comment = comment or ''
        request.save()
        if approve:
            attach_pdf(request, signed=True)
            send_approved_email(request)
        updated.append(request)
    return updated


def attach_pdf(request, *, signed):
    from apps.holidays.pdf import render_request_pdf

    content = render_request_pdf(request, signed=signed)
    filename = f'holiday-{request.pk}.pdf'
    if request.pdf_file:
        request.pdf_file.delete(save=False)
    request.pdf_file.save(filename, ContentFile(content), save=True)


def send_approved_email(request):
    from apps.core.mail import send_therese_html_email
    from apps.core.models import GlobalSetting
    from django.core.mail import EmailMultiAlternatives
    from django.conf import settings as django_settings
    from django.utils.html import strip_tags

    setting = GlobalSetting.get_solo()
    raw = getattr(setting, 'holiday_email_recipients', '') or ''
    recipients = [part.strip() for part in raw.replace(';', ',').split(',') if part.strip()]
    if not recipients:
        return
    subject = getattr(setting, 'holiday_email_subject', '') or 'Holiday request'
    html = getattr(setting, 'holiday_email_html', '') or (
        f'Holiday request for {request.employee.get_full_name()} '
        f'{request.start_date}–{request.end_date} ({request.day_count} days).'
    )
    from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', '') or None
    message = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html),
        from_email=from_email,
        to=recipients,
    )
    message.attach_alternative(html, 'text/html')
    if request.pdf_file:
        request.pdf_file.open('rb')
        try:
            message.attach(
                f'holiday-{request.pk}.pdf',
                request.pdf_file.read(),
                'application/pdf',
            )
        finally:
            request.pdf_file.close()
    message.send(fail_silently=True)
    # Keep helper import used if templates call it later.
    _ = send_therese_html_email


def ensure_default_rates():
    for weekdays, values in DEFAULT_RATES.items():
        for idx, days in enumerate(values):
            months = 12 - idx
            HolidayEntitlementRate.objects.get_or_create(
                weekdays=weekdays,
                contract_months=months,
                defaults={'days': days},
            )


def gantt_employees(user, *, workgroup_id=None, institute=False):
    from apps.hr.models import Employee

    qs = Employee.objects.institute().filter(holiday_profile__share_with_institute=True)
    viewer = getattr(user, 'employee', None)
    if institute:
        return qs.distinct().order_by('last_name', 'first_name')
    if workgroup_id:
        return qs.filter(workgroups__pk=workgroup_id).distinct().order_by(
            'last_name', 'first_name',
        )
    if viewer:
        ids = list(viewer.workgroups.values_list('pk', flat=True))
        if ids:
            return qs.filter(workgroups__in=ids).distinct().order_by(
                'last_name', 'first_name',
            )
    return qs.none()


def gantt_bars(employees, year):
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    year_days = (end - start).days + 1
    rows = []
    requests = HolidayRequest.objects.filter(
        employee__in=employees,
        status=HolidayRequest.Status.APPROVED,
        start_date__lte=end,
        end_date__gte=start,
    ).select_related('employee')
    by_emp = {}
    for request in requests:
        by_emp.setdefault(request.employee_id, []).append(request)
    for employee in employees:
        bars = []
        for request in by_emp.get(employee.pk, []):
            bar_start = max(request.start_date, start)
            bar_end = min(request.end_date, end)
            left = (bar_start - start).days / year_days * 100
            width = ((bar_end - bar_start).days + 1) / year_days * 100
            bars.append({
                'request': request,
                'left': left,
                'width': max(width, 0.4),
                'label': f'{request.start_date:%d.%m.}–{request.end_date:%d.%m.}',
            })
        rows.append({'employee': employee, 'bars': bars})
    return rows, year_days
