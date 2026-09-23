"""Occupational-group salary tables (hours → monthly pay)."""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

HOURS_QUANT = Decimal('0.001')
MONEY_QUANT = Decimal('0.01')


def quantize_hours(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value)).quantize(HOURS_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


def quantize_money(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


def format_hours_label(hours):
    hours = quantize_hours(hours)
    if hours is None:
        return ''
    text = format(hours, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text


def default_fulltime_hours():
    from apps.core.models import GlobalSetting
    hours = quantize_hours(GlobalSetting.get_default_weekly_hours())
    return hours or Decimal('39.000')


def fulltime_salary_from_row(row, *, fulltime_hours=None):
    """Convert row pay (for its hours) into a 100% monthly salary."""
    if row is None:
        return None
    hours = quantize_hours(row.weekly_hours)
    pay = quantize_money(row.monthly_salary)
    if not hours or hours <= 0 or pay is None:
        return None
    base = fulltime_hours if fulltime_hours is not None else default_fulltime_hours()
    if not base or base <= 0:
        return pay
    return (pay * base / hours).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def instance_on(table, as_of=None):
    if not table:
        return None
    if hasattr(table, 'instance_on'):
        return table.instance_on(as_of)
    from datetime import date
    as_of = as_of or date.today()
    return (
        table.instances.filter(effective_as_of__lte=as_of)
        .order_by('-effective_as_of')
        .first()
    )


def add_occupation_row(table, hours, pay, *, as_of=None):
    """Test/helper: ensure an instance on as_of and add a hours→pay row."""
    from datetime import date

    from apps.core.models import OccupationSalaryInstance, OccupationSalaryRow

    as_of = as_of or date(2000, 1, 1)
    instance, _ = OccupationSalaryInstance.objects.get_or_create(
        table=table, effective_as_of=as_of,
    )
    return OccupationSalaryRow.objects.create(
        instance=instance,
        weekly_hours=quantize_hours(hours),
        monthly_salary=quantize_money(pay),
    )


def row_for_hours(table, hours, as_of=None):
    if not table:
        return None
    hours = quantize_hours(hours)
    if hours is None:
        return None
    instance = instance_on(table, as_of)
    if instance is None:
        return None
    for row in instance.rows.all():
        if quantize_hours(row.weekly_hours) == hours:
            return row
    return None


def hours_choices(table, as_of=None):
    if not table:
        return []
    instance = instance_on(table, as_of)
    if instance is None:
        return []
    rows = list(instance.rows.all())
    rows.sort(key=lambda r: r.weekly_hours)
    return [
        (str(quantize_hours(r.weekly_hours)), f'{format_hours_label(r.weekly_hours)} h')
        for r in rows
    ]


def resolve_salary_table(employee=None, job=None):
    if employee is not None and getattr(employee, 'salary_table_id', None):
        return employee.salary_table
    job = job or (getattr(employee, 'job', None) if employee is not None else None)
    if job is not None and getattr(job, 'salary_table_id', None):
        return job.salary_table
    return None


def table_payload(table, as_of=None):
    if not table:
        return None
    fulltime = default_fulltime_hours()
    instance = instance_on(table, as_of)
    rows = []
    if instance is not None:
        for row in instance.rows.all():
            hours = quantize_hours(row.weekly_hours)
            pay = quantize_money(row.monthly_salary)
            rows.append({
                'hours': str(hours) if hours is not None else '',
                'pay': str(pay) if pay is not None else '',
                'fulltime': str(fulltime_salary_from_row(row, fulltime_hours=fulltime) or ''),
                'label': f'{format_hours_label(row.weekly_hours)} h',
            })
        rows.sort(key=lambda item: Decimal(item['hours'] or '0'))
    return {'id': table.pk, 'name': table.name, 'rows': rows}


def all_tables_payload():
    from apps.core.models import OccupationSalaryTable

    tables = OccupationSalaryTable.objects.prefetch_related('instances__rows').order_by('name')
    return [table_payload(table) for table in tables]


def salary_source_choices(*, include_empty=False):
    from apps.core.models import OccupationSalaryTable

    choices = [('tvl', 'TV-L')]
    choices.extend(
        (str(pk), name)
        for pk, name in OccupationSalaryTable.objects.order_by('name').values_list('pk', 'name')
    )
    if include_empty:
        return [('', '— Select salary table —')] + choices
    return choices


def table_from_id(value):
    from apps.core.models import OccupationSalaryTable

    if value in (None, '', 'tvl'):
        return None
    return OccupationSalaryTable.objects.filter(pk=value).first()


def table_from_employee_post(post, employee=None):
    """Resolve the table from an employee-form POST, else inherit from job."""
    if post is not None and 'salary_table' in post:
        raw = (post.get('salary_table') or '').strip()
        if raw:
            return table_from_id(raw)
        job = getattr(employee, 'job', None) if employee is not None else None
        job_id = post.get('job')
        if job_id:
            from apps.tasks.models import RecruitmentJob
            posted_job = (
                RecruitmentJob.objects.filter(pk=job_id)
                .select_related('salary_table')
                .first()
            )
            if posted_job is not None:
                job = posted_job
        if job is not None and getattr(job, 'salary_table_id', None):
            return job.salary_table
        return None
    return resolve_salary_table(employee)


def employee_salary_table_ids():
    from apps.hr.models import Employee

    mapping = {}
    qs = Employee.objects.visible().select_related('salary_table', 'job__salary_table')
    for emp in qs:
        table = resolve_salary_table(emp)
        if table is not None:
            mapping[str(emp.pk)] = table.pk
    return mapping


def occupation_tables_for_settings():
    from datetime import date

    from apps.core.models import OccupationSalaryTable

    today = date.today()
    result = []
    tables = OccupationSalaryTable.objects.prefetch_related('instances__rows').order_by('name')
    for table in tables:
        active = table.instance_on(today)
        instances = []
        for inst in table.instances.all():
            instances.append({
                'pk': inst.pk,
                'effective_as_of': inst.effective_as_of,
                'date_iso': inst.effective_as_of.isoformat(),
                'is_active': active is not None and inst.pk == active.pk,
                'rows': list(inst.rows.all()),
            })
        result.append({
            'pk': table.pk,
            'name': table.name,
            'instances': instances,
        })
    return result


def occupation_form_context():
    from apps.core.models import GlobalSetting

    return {
        'occupation_tables_json': all_tables_payload(),
        'employee_salary_table_ids_json': employee_salary_table_ids(),
        'default_weekly_hours': GlobalSetting.get_default_weekly_hours(),
    }


def parse_instance_date(raw):
    from datetime import datetime

    text = str(raw or '').strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _save_instance_rows(post, prefix, instance):
    from apps.core.models import OccupationSalaryRow
    from apps.tasks.form_validation import parse_loose_decimal

    keep_row_ids = set()
    row_index = 0
    seen_hours = set()
    while True:
        row_prefix = f'{prefix}row_{row_index}_'
        if f'{row_prefix}hours' not in post and f'{row_prefix}id' not in post:
            break
        row_index += 1
        if post.get(f'{row_prefix}delete') in ('1', 'on', 'true'):
            row_pk = post.get(f'{row_prefix}id')
            if row_pk:
                OccupationSalaryRow.objects.filter(pk=row_pk, instance=instance).delete()
            continue
        try:
            hours = quantize_hours(parse_loose_decimal(post.get(f'{row_prefix}hours')))
            pay_raw = post.get(f'{row_prefix}pay')
            pay = quantize_money(parse_loose_decimal(pay_raw)) if str(pay_raw or '').strip() else Decimal('0.00')
        except (InvalidOperation, TypeError, ValueError):
            continue
        if hours is None or hours <= 0:
            continue
        if hours in seen_hours:
            continue
        seen_hours.add(hours)
        if pay is None:
            pay = Decimal('0.00')
        row_pk = post.get(f'{row_prefix}id')
        row = OccupationSalaryRow.objects.filter(pk=row_pk, instance=instance).first() if row_pk else None
        if row:
            row.weekly_hours = hours
            row.monthly_salary = pay
            row.save(update_fields=['weekly_hours', 'monthly_salary', 'updated_at'])
        else:
            row = OccupationSalaryRow.objects.create(
                instance=instance, weekly_hours=hours, monthly_salary=pay,
            )
        keep_row_ids.add(row.pk)
    OccupationSalaryRow.objects.filter(instance=instance).exclude(pk__in=keep_row_ids).delete()


@transaction.atomic
def save_occupation_tables_from_post(post):
    """Replace occupation tables from a Global Settings POST. No-op if marker missing."""
    if post.get('occ_tables_present') != '1':
        return
    from apps.core.models import OccupationSalaryInstance, OccupationSalaryTable

    keep_ids = set()
    index = 0
    while True:
        prefix = f'occ_table_{index}_'
        if f'{prefix}name' not in post and f'{prefix}id' not in post:
            break
        index += 1
        if post.get(f'{prefix}delete') in ('1', 'on', 'true'):
            pk = post.get(f'{prefix}id')
            if pk:
                table = OccupationSalaryTable.objects.filter(pk=pk).first()
                if table:
                    try:
                        table.delete()
                    except ProtectedError:
                        keep_ids.add(table.pk)
            continue
        name = (post.get(f'{prefix}name') or '').strip()
        if not name:
            continue
        pk = post.get(f'{prefix}id')
        table = OccupationSalaryTable.objects.filter(pk=pk).first() if pk else None
        if table:
            if table.name != name:
                table.name = name
                try:
                    table.save(update_fields=['name', 'updated_at'])
                except IntegrityError:
                    keep_ids.add(table.pk)
                    continue
        else:
            try:
                table = OccupationSalaryTable.objects.create(name=name)
            except IntegrityError:
                table = OccupationSalaryTable.objects.filter(name=name).first()
                if table is None:
                    continue
        keep_ids.add(table.pk)

        keep_inst_ids = set()
        inst_index = 0
        seen_dates = set()
        while True:
            inst_prefix = f'{prefix}inst_{inst_index}_'
            if f'{inst_prefix}date' not in post and f'{inst_prefix}id' not in post:
                break
            inst_index += 1
            if post.get(f'{inst_prefix}delete') in ('1', 'on', 'true'):
                inst_pk = post.get(f'{inst_prefix}id')
                if inst_pk:
                    OccupationSalaryInstance.objects.filter(pk=inst_pk, table=table).delete()
                continue
            as_of = parse_instance_date(post.get(f'{inst_prefix}date'))
            if as_of is None or as_of in seen_dates:
                continue
            seen_dates.add(as_of)
            inst_pk = post.get(f'{inst_prefix}id')
            instance = (
                OccupationSalaryInstance.objects.filter(pk=inst_pk, table=table).first()
                if inst_pk else None
            )
            if instance:
                if instance.effective_as_of != as_of:
                    instance.effective_as_of = as_of
                    try:
                        instance.save(update_fields=['effective_as_of', 'updated_at'])
                    except IntegrityError:
                        continue
            else:
                instance = OccupationSalaryInstance.objects.filter(
                    table=table, effective_as_of=as_of,
                ).first()
                if instance is None:
                    try:
                        instance = OccupationSalaryInstance.objects.create(
                            table=table, effective_as_of=as_of,
                        )
                    except IntegrityError:
                        instance = OccupationSalaryInstance.objects.filter(
                            table=table, effective_as_of=as_of,
                        ).first()
                        if instance is None:
                            continue
            keep_inst_ids.add(instance.pk)
            _save_instance_rows(post, inst_prefix, instance)
        OccupationSalaryInstance.objects.filter(table=table).exclude(pk__in=keep_inst_ids).delete()

    for leftover in OccupationSalaryTable.objects.exclude(pk__in=keep_ids):
        try:
            leftover.delete()
        except ProtectedError:
            pass
