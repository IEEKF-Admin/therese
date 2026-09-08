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
