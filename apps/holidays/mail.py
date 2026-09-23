"""Request and cancellation emails for holiday leave."""

from datetime import date
from decimal import Decimal

from django.conf import settings as django_settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape, strip_tags

from apps.core.models import GlobalSetting


HOLIDAY_EMAIL_VARIABLES = [
    {'key': 'applicant_name', 'label': 'Vorname und Nachname (mit Präfix)', 'token': '{{ applicant_name }}'},
    {'key': 'first_name', 'label': 'Vorname', 'token': '{{ first_name }}'},
    {'key': 'last_name', 'label': 'Nachname', 'token': '{{ last_name }}'},
    {'key': 'employee_number', 'label': 'Personalnummer', 'token': '{{ employee_number }}'},
    {'key': 'job_title', 'label': 'Dienstbezeichnung', 'token': '{{ job_title }}'},
    {'key': 'department', 'label': 'Geschäftsbereich / Abteilung', 'token': '{{ department }}'},
    {'key': 'request_date', 'label': 'Antragsdatum (TT.MM.JJJJ)', 'token': '{{ request_date }}'},
    {'key': 'place_date', 'label': 'Ort, den Datum', 'token': '{{ place_date }}'},
    {'key': 'vacation_from', 'label': 'Urlaub vom', 'token': '{{ vacation_from }}'},
    {'key': 'vacation_until', 'label': 'Urlaub bis', 'token': '{{ vacation_until }}'},
    {'key': 'periods', 'label': 'Zeiträume (ggf. mehrere)', 'token': '{{ periods }}'},
    {'key': 'day_count', 'label': 'Arbeitstage dieser Meldung', 'token': '{{ day_count }}'},
    {'key': 'purpose', 'label': 'Anlass / Zweck', 'token': '{{ purpose }}'},
    {'key': 'leave_address', 'label': 'Urlaubsanschrift', 'token': '{{ leave_address }}'},
    {'key': 'deputy', 'label': 'Vertreter/in (leer, nicht erfasst)', 'token': '{{ deputy }}'},
    {'key': 'annual_leave', 'label': 'Zustehender Jahresurlaub', 'token': '{{ annual_leave }}'},
    {'key': 'special_leave', 'label': 'Zusatz-Sonder-Urlaub', 'token': '{{ special_leave }}'},
    {'key': 'carryover', 'label': 'Rest aus Vorjahr', 'token': '{{ carryover }}'},
    {'key': 'available', 'label': 'zusammen', 'token': '{{ available }}'},
    {'key': 'already_granted', 'label': 'davon bereits erhalten/genehmigt', 'token': '{{ already_granted }}'},
    {'key': 'now_requested', 'label': 'jetzt erbeten', 'token': '{{ now_requested }}'},
    {'key': 'remaining_leave', 'label': 'verbleibender Resturlaub', 'token': '{{ remaining_leave }}'},
    {'key': 'holiday_analysis', 'label': 'Jahresübersicht', 'token': '{{ holiday_analysis }}'},
    {'key': 'approver_name', 'label': 'Präfix und Nachname der freigebenden Person', 'token': '{{ approver_name }}'},
]

HOLIDAY_EMAIL_VARIABLE_HELP = ', '.join(
    '{{ ' + item['key'] + ' }}' for item in HOLIDAY_EMAIL_VARIABLES
)

DEFAULT_REQUEST_SUBJECT = 'Urlaubsantrag – {{ applicant_name }}'
DEFAULT_REQUEST_HTML = (
    '<p>{{ first_name }} {{ last_name }}<br>'
    '{{ job_title }}<br>'
    '{{ department }}</p>'
    '<p>{{ place_date }}</p>'
    '<p><strong>URLAUBSANTRAG</strong></p>'
    '<p>Ich bitte um Urlaub vom {{ vacation_from }} bis {{ vacation_until }}'
    ' ({{ day_count }} Arbeitstage).</p>'
    '<p>Anlass, Zweck des Urlaubs: {{ purpose }}<br>'
    'Urlaubsanschrift: {{ leave_address }}<br>'
    'Vertreter/in: {{ deputy }}</p>'
    '<p>Zustehender Jahresurlaub: {{ annual_leave }} Arbeitstage<br>'
    'Zusatz-Sonder-Urlaub: {{ special_leave }}<br>'
    'Rest aus Vorjahr: {{ carryover }}<br>'
    'zusammen: {{ available }}<br>'
    'davon bereits erhalten/genehmigt: {{ already_granted }}<br>'
    'jetzt erbeten: {{ now_requested }}<br>'
    'verbleibender Resturlaub: {{ remaining_leave }} Arbeitstage</p>'
    '<p>Freigegeben von: {{ approver_name }}</p>'
)
DEFAULT_CANCEL_SUBJECT = 'Urlaubsstornierung – {{ applicant_name }}'
DEFAULT_CANCEL_HTML = (
    '<p>{{ applicant_name }} (Personalnummer {{ employee_number }}) '
    'hat Urlaub storniert:</p><p>{{ periods }}</p>'
    '<p>Tage: {{ day_count }}</p>'
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
            parts.append(f'{first.strftime("%d.%m.%Y")} bis {last.strftime("%d.%m.%Y")}')
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
            f'{year}: verfügbar {format_days(balance["available"])}, '
            f'genehmigt {format_days(balance["approved"])}, '
            f'beantragt {format_days(balance["pending"])}, '
            f'verbleibend {format_days(balance["remaining"])}'
        )
    return '\n'.join(lines)


def format_german_date(value):
    if value is None:
        return ''
    if hasattr(value, 'date'):
        value = value.date()
    return value.strftime('%d.%m.%Y')


def format_leave_address(employee):
    if not employee:
        return ''
    street = ' '.join(
        part for part in (
            (getattr(employee, 'street', '') or '').strip(),
            (getattr(employee, 'house_number', '') or '').strip(),
        ) if part
    )
    city = ' '.join(
        part for part in (
            (getattr(employee, 'postal_code', '') or '').strip(),
            (getattr(employee, 'city', '') or '').strip(),
        ) if part
    )
    return '\n'.join(part for part in (street, city) if part)


def format_approver_name(user):
    if not user:
        return ''
    employee = getattr(user, 'employee', None)
    if employee is not None:
        prefix = (employee.prefix or '').strip()
        last_name = (employee.last_name or '').strip()
        return f'{prefix} {last_name}'.strip()
    last_name = (getattr(user, 'last_name', '') or '').strip()
    return last_name


def format_department(employee):
    if not employee:
        return ''
    names = []
    for group in employee.workgroups.all():
        label = (group.long_name or group.short_name or '').strip()
        if label and label not in names:
            names.append(label)
    return ', '.join(names)


def render_holiday_template(template, context, *, html=False):
    text = template or ''
    for key, value in context.items():
        rendered = str(value)
        if html:
            rendered = escape(rendered).replace('\n', '<br>')
        text = text.replace('{{ ' + key + ' }}', rendered)
        text = text.replace('{{' + key + '}}', rendered)
    return text


def holiday_mail_context(employee, dates, *, holiday_request=None):
    from apps.holidays.services import entitlement_breakdown, used_days
    from apps.holidays.models import HolidayRequest

    days = sorted({day if isinstance(day, date) else date.fromisoformat(str(day)) for day in dates})
    years = [day.year for day in days]
    first_name = (getattr(employee, 'first_name', '') or '').strip() if employee else ''
    last_name = (getattr(employee, 'last_name', '') or '').strip() if employee else ''
    full_name = employee.get_full_name() if employee else ''
    job = getattr(employee, 'job', None) if employee else None
    job_title = (getattr(job, 'name', '') or '').strip() if job else ''
    submitted = None
    if holiday_request is not None:
        submitted = getattr(holiday_request, 'submitted_at', None)
    request_day = submitted.date() if submitted else date.today()
    city = ((getattr(employee, 'city', '') or '').strip() if employee else '') or 'Bonn'
    comment = ''
    if holiday_request is not None:
        comment = (holiday_request.comment or '').strip()
    purpose = comment or 'Erholungsurlaub'
    primary_year = days[0].year if days else date.today().year
    exclude_pk = holiday_request.pk if holiday_request is not None else None
    breakdown = entitlement_breakdown(employee, primary_year) if employee else {
        'holidays': Decimal('0'),
        'carryover': Decimal('0'),
        'special_leave': Decimal('0'),
        'available': Decimal('0'),
    }
    already_granted = used_days(
        employee,
        primary_year,
        exclude_pk=exclude_pk,
        statuses=(HolidayRequest.Status.APPROVED,),
    ) if employee else Decimal('0')
    now_requested = Decimal(sum(1 for day in days if day.year == primary_year))
    remaining_leave = breakdown['available'] - already_granted - now_requested
    decided_by = getattr(holiday_request, 'decided_by', None) if holiday_request is not None else None
    return {
        'applicant_name': full_name,
        'first_name': first_name,
        'last_name': last_name,
        'employee_number': getattr(employee, 'employee_number', '') or '',
        'job_title': job_title,
        'department': format_department(employee),
        'request_date': format_german_date(request_day),
        'place_date': f'{city}, den {format_german_date(request_day)}',
        'vacation_from': format_german_date(days[0]) if days else '',
        'vacation_until': format_german_date(days[-1]) if days else '',
        'periods': format_leave_periods(days),
        'day_count': str(Decimal(len(days))),
        'purpose': purpose,
        'leave_address': format_leave_address(employee),
        'deputy': '',
        'annual_leave': format_days(breakdown['holidays']),
        'special_leave': format_days(breakdown['special_leave']),
        'carryover': format_days(breakdown['carryover']),
        'available': format_days(breakdown['available']),
        'already_granted': format_days(already_granted),
        'now_requested': format_days(now_requested),
        'remaining_leave': format_days(remaining_leave),
        'holiday_analysis': format_holiday_analysis(employee, years) if employee else '',
        'approver_name': format_approver_name(decided_by),
    }


def send_holiday_lifecycle_email(kind, employee, dates, *, holiday_request=None):
    """kind is 'request' or 'cancel'."""
    recipients = holiday_mail_recipients(employee)
    if not recipients or not dates:
        return False
    setting = GlobalSetting.get_solo()
    context = holiday_mail_context(employee, dates, holiday_request=holiday_request)
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
