"""Helpers for the recurring schedule message trigger."""

from datetime import datetime, timedelta

from django.utils import timezone

WEEKDAY_CHOICES = [
    (0, 'Monday'),
    (1, 'Tuesday'),
    (2, 'Wednesday'),
    (3, 'Thursday'),
    (4, 'Friday'),
    (5, 'Saturday'),
    (6, 'Sunday'),
]
WEEKDAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

SCHEDULE_REQUIRE_LIST_PREFIXES = (
    'purchase_orders',
    'my_purchase_orders',
    'assigned_tasks',
    'unopened_tasks',
    'personnel_tasks',
    'my_personnel_tasks',
    'ending_contracts',
)


def parse_schedule_weekdays(raw):
    days = []
    for part in str(raw or '').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            number = int(part)
        except ValueError:
            continue
        if 0 <= number <= 6:
            days.append(number)
    return sorted(set(days))


def encode_schedule_weekdays(values):
    days = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= number <= 6:
            days.append(number)
    return ','.join(str(day) for day in sorted(set(days)))


def schedule_reference_key(day):
    return f'schedule:{day.isoformat()}'


def _aware_occurrence(day, schedule_time):
    naive = datetime.combine(day, schedule_time)
    tzinfo = timezone.get_current_timezone()
    return timezone.make_aware(naive, tzinfo)


def last_due_schedule_occurrence(config, now=None):
    """Most recent weekday+time that has already started, looking back 8 days."""
    schedule_time = getattr(config, 'schedule_time', None)
    if not schedule_time:
        return None
    weekdays = parse_schedule_weekdays(getattr(config, 'schedule_weekdays', ''))
    if not weekdays:
        return None
    local = timezone.localtime(now or timezone.now())
    for delta in range(0, 8):
        day = (local - timedelta(days=delta)).date()
        if day.weekday() not in weekdays:
            continue
        occurrence = _aware_occurrence(day, schedule_time)
        if occurrence <= local:
            return day, schedule_reference_key(day)
    return None


def schedule_require_list_choices():
    from apps.accounts.template_variables import VARIABLES

    choices = []
    for var in VARIABLES:
        if var.get('group') != 'lists':
            continue
        key = var['key']
        if any(key == prefix or key.startswith(prefix + '_') for prefix in SCHEDULE_REQUIRE_LIST_PREFIXES):
            choices.append((key, var['label']))
    return choices


def parse_schedule_require_lists(raw):
    allowed = {key for key, _label in schedule_require_list_choices()}
    keys = []
    for part in str(raw or '').split(','):
        key = part.strip()
        if key and key in allowed and key not in keys:
            keys.append(key)
    return keys


def encode_schedule_require_lists(values):
    allowed = {key for key, _label in schedule_require_list_choices()}
    keys = []
    for value in values or []:
        key = str(value).strip()
        if key in allowed and key not in keys:
            keys.append(key)
    return ','.join(keys)


def list_value_is_empty(value):
    from apps.accounts.template_variables import TemplateList

    if value is None:
        return True
    if isinstance(value, TemplateList):
        return not value.rows
    text = str(value).strip()
    return text in ('', 'None', '—', '-')


def required_lists_are_filled(config, user, employee, replacements=None):
    keys = parse_schedule_require_lists(getattr(config, 'schedule_require_lists', ''))
    if not keys:
        return True
    if replacements is None:
        from apps.accounts.template_variables import build_replacement_map

        replacements = build_replacement_map(user, employee)
    return all(not list_value_is_empty(replacements.get(key)) for key in keys)


def current_due_schedule_occurrence(config, now=None):
    """Today's occurrence if it is already due."""
    last = last_due_schedule_occurrence(config, now=now)
    if not last:
        return None
    day, key = last
    local = timezone.localtime(now or timezone.now())
    if day != local.date():
        return None
    return day, key
