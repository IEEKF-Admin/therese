"""Request and cancellation emails for holiday leave."""

from datetime import date
from decimal import Decimal

from django.conf import settings as django_settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape, strip_tags

from apps.core.models import GlobalSetting


DEFAULT_REQUEST_SUBJECT = 'Holiday request – {{ applicant_name }}'
DEFAULT_REQUEST_HTML = (
    '<p>{{ applicant_name }} (personnel number {{ employee_number }}) '
    'has requested leave:</p><p>{{ periods }}</p>'
    '<p>Days: {{ day_count }}</p>'
)
DEFAULT_CANCEL_SUBJECT = 'Holiday cancellation – {{ applicant_name }}'
DEFAULT_CANCEL_HTML = (
    '<p>{{ applicant_name }} (personnel number {{ employee_number }}) '
    'has cancelled leave:</p><p>{{ periods }}</p>'
    '<p>Days: {{ day_count }}</p>'
)


def format_leave_periods(dates):
    days = sorted({day if isinstance(day, date) else date.fromisoformat(str(day)) for day in dates})
    if not days:
        return ''
    groups = []
    start = prev = days[0]
    for day in days[1:]:
        gap = (day - prev).days
        weekend_gap = gap <= 3 and prev.weekday() >= 4 and day.weekday() <= 1
        if gap == 1 or weekend_gap:
            prev = day
        else:
            groups.append((start, prev))
            start = prev = day
    groups.append((start, prev))
    parts = []
    for first, last in groups:
        if first == last:
            parts.append(first.strftime('%d.%m.%Y'))
        else:
            parts.append(f'{first.strftime("%d.%m.%Y")}–{last.strftime("%d.%m.%Y")}')
    return ', '.join(parts)


def holiday_mail_recipients(employee):
    setting = GlobalSetting.get_solo()
    raw = getattr(setting, 'holiday_email_recipients', '') or ''
    recipients = [part.strip() for part in raw.replace(';', ',').split(',') if part.strip()]
    extra = (getattr(employee, 'email_professional', '') or getattr(employee, 'email_private', '') or '').strip()
    if extra and extra not in recipients:
        recipients.append(extra)
    return recipients


def format_days(value):
    amount = Decimal(value)
    if amount == amount.to_integral_value():
        return str(int(amount))
    return f'{amount:.1f}'


def format_holiday_analysis(employee, years):
    from apps.holidays.services import year_balance

    lines = []
    for year in sorted({int(item) for item in years}):
        balance = year_balance(employee, year)
        lines.append(
            f'{year}: available {format_days(balance["available"])}, '
            f'granted {format_days(balance["approved"])}, '
            f'applied {format_days(balance["pending"])}, '
            f'remaining {format_days(balance["remaining"])}'
        )
    return '\n'.join(lines)


def render_holiday_template(template, context, *, html=False):
    text = template or ''
    for key, value in context.items():
        rendered = str(value)
        if html:
            rendered = escape(rendered).replace('\n', '<br>')
        text = text.replace('{{ ' + key + ' }}', rendered)
        text = text.replace('{{' + key + '}}', rendered)
    return text


def _mail_context(employee, dates):
    days = sorted({day if isinstance(day, date) else date.fromisoformat(str(day)) for day in dates})
    years = [day.year for day in days]
    return {
        'applicant_name': employee.get_full_name() if employee else '',
        'employee_number': getattr(employee, 'employee_number', '') or '',
        'periods': format_leave_periods(days),
        'day_count': str(Decimal(len(days))),
        'holiday_analysis': format_holiday_analysis(employee, years),
    }


def send_holiday_lifecycle_email(kind, employee, dates):
    """kind is 'request' or 'cancel'."""
    recipients = holiday_mail_recipients(employee)
    if not recipients or not dates:
        return False
    setting = GlobalSetting.get_solo()
    context = _mail_context(employee, dates)
    if kind == 'cancel':
        subject_tpl = getattr(setting, 'holiday_cancel_email_subject', '') or DEFAULT_CANCEL_SUBJECT
        html_tpl = getattr(setting, 'holiday_cancel_email_html', '') or DEFAULT_CANCEL_HTML
    else:
        subject_tpl = getattr(setting, 'holiday_request_email_subject', '') or DEFAULT_REQUEST_SUBJECT
        html_tpl = getattr(setting, 'holiday_request_email_html', '') or DEFAULT_REQUEST_HTML
    subject = render_holiday_template(subject_tpl, context, html=False).strip() or 'Holiday request'
    html = render_holiday_template(html_tpl, context, html=True)
    from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', '') or None
    message = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html),
        from_email=from_email,
        to=recipients,
    )
    message.attach_alternative(html, 'text/html')
    message.send(fail_silently=True)
    return True
