"""WordPress enrollment: payload, workgroup assignment, mark, publish."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os

from django.utils import timezone

from apps.core.wordpress import (
    WordPressError,
    create_wordpress_post,
    unpublish_wordpress_post,
    update_wordpress_post,
)

SOURCE_KEYS = (
    'posttitle',
    'name',
    'linkmember',
    'phone',
    'mobile',
    'email',
    'address',
    'picture',
)
POPUP_KEYS = ('position', 'websideadressfield', 'linkfieldaddress')
TEXT_KEYS = SOURCE_KEYS[:-1] + POPUP_KEYS


def wordpress_position_choices(setting=None):
    from apps.core.models import GlobalSetting

    setting = setting or GlobalSetting.get_solo()
    values = []
    for line in (setting.wordpress_positions or '').splitlines():
        value = line.strip()
        if value and value not in values:
            values.append(value)
    return values


WP_QUEUE_SESSION = 'accounts_wp_queue'


def configured_sites():
    from apps.hr.models import WordPressSite

    return list(
        WordPressSite.objects.exclude(url='')
        .prefetch_related('workgroups')
        .order_by('name')
    )


def picture_identity(employee) -> str:
    field = getattr(employee, 'profile_picture', None)
    if not field:
        return ''
    try:
        name = field.name or ''
        size = field.size
    except Exception:
        return getattr(field, 'name', '') or ''
    if not name:
        return ''
    return f'{name}:{size}'


def source_payload(employee) -> dict:
    address = ''
    room = getattr(employee, 'room', None)
    if room is not None:
        building = getattr(room, 'building', None)
        if building is not None:
            address = building.address or ''
    number = (getattr(employee, 'employee_number', None) or '').strip()
    first = (employee.first_name or '').strip()
    last = (employee.last_name or '').strip()
    return {
        'posttitle': f'{number} {first} {last}'.strip(),
        'name': f'{first} {last}'.strip(),
        'linkmember': (employee.website or '').strip(),
        'phone': (employee.phone_number or '').strip(),
        'mobile': (employee.private_phone_number or '').strip(),
        'email': (employee.email_professional or '').strip(),
        'address': address,
        'picture': picture_identity(employee),
    }


def source_changed(enrollment, employee) -> list[str]:
    current = source_payload(employee)
    last = enrollment.last_source or {}
    changed = []
    for key in SOURCE_KEYS:
        if str(current.get(key) or '') != str(last.get(key) or ''):
            changed.append(key)
    return changed


def employee_assigned_to_site(employee, site) -> bool:
    site_ids = {wg.pk for wg in site.workgroups.all()}
    if not site_ids:
        return False
    emp_ids = {wg.pk for wg in employee.workgroups.all()}
    return bool(site_ids & emp_ids)


def _enrollment_map(employee):
    return {row.site_id: row for row in employee.wordpress_enrollments.all()}


def _source_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]


def _attention_key(employee, site, reason: str, source: dict) -> str:
    if reason == 'Unpublish':
        return f'wp:{employee.pk}:{site.pk}:unpublish'
    return f'wp:{employee.pk}:{site.pk}:update:{_source_hash(source)}'


def _notify(employee, site, reason: str, changed_fields: list[str], source: dict):
    from apps.accounts.trigger_emails import notify_wordpress_update_needed

    notify_wordpress_update_needed(
        {
            'employee': employee,
            'site': site,
            'reason': reason,
            'changed_fields': ', '.join(changed_fields),
        },
        _attention_key(employee, site, reason, source)[:191],
    )


def site_state(employee, site, enrollment=None) -> dict:
    assigned = employee_assigned_to_site(employee, site)
    source = source_payload(employee)
    last_sent = (enrollment.last_sent if enrollment else None) or {}
    published = bool(
        enrollment is not None
        and enrollment.status == enrollment.Status.PUBLISHED
        and (enrollment.posttitle or '')
    )
    changed = source_changed(enrollment, employee) if published else []
    leftover = published and not assigned
    needs_update = published and assigned and bool(changed)
    marked = leftover or needs_update
    icon = ''
    icon_class = ''
    if leftover:
        action = 'unpublish'
        label = 'Unpublish'
        reason = 'Unpublish'
        icon = 'fas fa-eye-slash'
        icon_class = 'is-attention'
    elif needs_update:
        action = 'update'
        label = 'Update needed'
        reason = 'Update needed'
        icon = 'fas fa-exclamation-circle'
        icon_class = 'is-attention'
    elif published:
        action = ''
        label = 'Shared'
        reason = ''
        icon = 'fas fa-check-circle'
        icon_class = 'is-shared'
    elif assigned:
        action = 'add'
        label = 'Add'
        reason = ''
        icon = 'fas fa-minus-circle'
        icon_class = 'is-missing'
    else:
        action = ''
        label = '—'
        reason = ''
    error_detail = ''
    if enrollment is not None and enrollment.status == enrollment.Status.ERROR:
        error_detail = enrollment.detail or 'Error'
        icon = 'fas fa-exclamation-triangle'
        icon_class = 'is-error'
        if assigned and not published:
            action = 'add'
            label = 'Add'
        elif published and assigned and not leftover:
            action = action or 'update'
    prefill = dict(source)
    prefill.pop('picture', None)
    for key in POPUP_KEYS:
        prefill[key] = last_sent.get(key) or ''
    picture_url = ''
    field = getattr(employee, 'profile_picture', None)
    if field:
        try:
            picture_url = field.url
        except Exception:
            picture_url = ''
    return {
        'site': site,
        'site_id': site.pk,
        'site_name': site.name,
        'assigned': assigned,
        'published': published,
        'action': action,
        'label': label,
        'icon': icon,
        'icon_class': icon_class,
        'marked': marked,
        'reason': reason,
        'changed_fields': changed,
        'detail': error_detail or ((enrollment.detail if enrollment else '') or ''),
        'posttitle': (enrollment.posttitle if enrollment else '') or source['posttitle'],
        'prefill': prefill,
        'has_picture': bool(source.get('picture')),
        'picture_url': picture_url,
        'enrollment_id': enrollment.pk if enrollment else None,
        'ack_key': _attention_key(employee, site, reason or 'Update needed', source) if marked else '',
    }


def employee_wordpress_states(employee, sites=None) -> list[dict]:
    sites = sites if sites is not None else configured_sites()
    by_site = _enrollment_map(employee)
    return [site_state(employee, site, by_site.get(site.pk)) for site in sites]


def marked_wordpress_states(employee=None, sites=None) -> list[dict]:
    from apps.hr.models import Employee

    sites = sites if sites is not None else configured_sites()
    if not sites:
        return []
    qs = Employee.objects.visible().select_related('room__building').prefetch_related(
        'workgroups',
        'wordpress_enrollments',
    )
    if employee is not None:
        qs = qs.filter(pk=employee.pk)
    marked = []
    for emp in qs:
        for state in employee_wordpress_states(emp, sites):
            if state['marked']:
                marked.append(state | {'employee': emp})
    return marked


def wordpress_attention_exists() -> bool:
    from apps.hr.models import EmployeeWordPressEnrollment

    return EmployeeWordPressEnrollment.objects.filter(needs_attention=True).exists()


def scan_employee_wordpress(employee, *, notify=True):
    from apps.hr.models import Employee

    if employee is None or not getattr(employee, 'pk', None):
        return
    employee = (
        Employee.objects.select_related('room__building')
        .prefetch_related('workgroups', 'wordpress_enrollments__site__workgroups')
        .filter(pk=employee.pk)
        .first()
    )
    if employee is None:
        return
    sites = configured_sites()
    by_site = _enrollment_map(employee)
    for site in sites:
        enrollment = by_site.get(site.pk)
        if enrollment is None:
            continue
        state = site_state(employee, site, enrollment)
        should = bool(state['marked'])
        was_marked = enrollment.needs_attention
        if was_marked != should:
            enrollment.needs_attention = should
            enrollment.save(update_fields=['needs_attention', 'updated_at'])
        if should and notify and not was_marked:
            _notify(
                employee,
                site,
                state['reason'],
                state['changed_fields'],
                source_payload(employee),
            )


def scan_employees_for_building(building):
    from apps.hr.models import Employee

    if building is None:
        return
    for employee in Employee.objects.filter(room__building=building).iterator():
        scan_employee_wordpress(employee)


def scan_wordpress_site(site):
    from apps.hr.models import Employee

    if site is None:
        return
    emp_ids = set(site.enrollments.values_list('employee_id', flat=True))
    emp_ids.update(
        Employee.objects.filter(workgroups__in=site.workgroups.all()).values_list('pk', flat=True)
    )
    for employee in Employee.objects.filter(pk__in=emp_ids).iterator():
        scan_employee_wordpress(employee)


def list_wordpress_updates(limit=50) -> list:
    from apps.accounts.template_variables import TemplateList

    rows = []
    extra = 0
    for state in marked_wordpress_states():
        if len(rows) >= limit:
            extra += 1
            continue
        emp = state['employee']
        rows.append((
            f'{emp.last_name}, {emp.first_name}',
            emp.employee_number or '',
            state['site_name'],
            state['reason'] or state['label'],
            ', '.join(state['changed_fields']),
        ))
    if extra:
        rows.append((f'… and {extra} more', '', '', '', ''))
    return TemplateList(
        ['Employee', 'Number', 'Site', 'Reason', 'Changed'],
        rows,
        empty_label='None',
    )


def profile_picture_file(employee):
    field = getattr(employee, 'profile_picture', None)
    if not field:
        return None
    try:
        field.open('rb')
        content = field.read()
        name = os.path.basename(field.name) or 'picture'
        field.close()
    except Exception:
        return None
    if not content:
        return None
    ctype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return (name, content, ctype)


def _picture_from_upload(uploaded):
    if uploaded is None:
        return None
    name = os.path.basename(getattr(uploaded, 'name', '') or 'picture')
    content = uploaded.read()
    if not content:
        return None
    ctype = getattr(uploaded, 'content_type', None) or mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return (name, content, ctype)


def _text_fields(raw: dict) -> dict:
    out = {}
    for key in TEXT_KEYS:
        value = raw.get(key)
        if value is None:
            value = ''
        value = str(value)
        if key == 'address':
            value = value.replace('\r\n', '\n').replace('\r', '\n')
        else:
            value = value.strip()
        out[key] = value
    return out


def publish_employee_to_site(employee, site, fields, picture_upload=None):
    from apps.hr.models import EmployeeWordPressEnrollment

    if not site.is_configured():
        raise WordPressError('WordPress site is missing URL, user, or application password.')
    if not employee_assigned_to_site(employee, site):
        raise WordPressError('This employee is not in a workgroup mapped to this site.')
    payload = _text_fields(fields)
    posttitle = payload.get('posttitle') or ''
    if not posttitle:
        raise WordPressError('posttitle is required.')
    enrollment = EmployeeWordPressEnrollment.objects.filter(
        employee=employee, site=site,
    ).first()
    picture = _picture_from_upload(picture_upload)
    source = source_payload(employee)
    published = bool(
        enrollment is not None
        and enrollment.status == EmployeeWordPressEnrollment.Status.PUBLISHED
        and (enrollment.posttitle or '')
    )
    try:
        if not published:
            if picture is None:
                picture = profile_picture_file(employee)
            result = create_wordpress_post(site, payload, picture)
        else:
            send_picture = picture
            if send_picture is None and source.get('picture') != (enrollment.last_source or {}).get('picture'):
                send_picture = profile_picture_file(employee)
            lookup_title = enrollment.posttitle
            update_fields = dict(payload)
            if posttitle != lookup_title:
                update_fields['new_posttitle'] = posttitle
            result = update_wordpress_post(site, lookup_title, update_fields, send_picture)
    except WordPressError as exc:
        if enrollment is None:
            EmployeeWordPressEnrollment.objects.create(
                employee=employee,
                site=site,
                posttitle=posttitle,
                status=EmployeeWordPressEnrollment.Status.ERROR,
                detail=str(exc),
            )
        else:
            enrollment.detail = str(exc)
            if not published:
                enrollment.status = EmployeeWordPressEnrollment.Status.ERROR
            enrollment.save(update_fields=['detail', 'status', 'updated_at'])
        raise
    now = timezone.now()
    last_sent = dict(payload)
    last_sent['picture'] = source.get('picture') or ''
    defaults = {
        'posttitle': (result.get('posttitle') if isinstance(result, dict) else None) or posttitle,
        'wp_post_id': (result.get('id') if isinstance(result, dict) else None) or None,
        'status': EmployeeWordPressEnrollment.Status.PUBLISHED,
        'last_source': source,
        'last_sent': last_sent,
        'detail': '',
        'needs_attention': False,
        'last_synced_at': now,
    }
    if enrollment is None:
        enrollment = EmployeeWordPressEnrollment.objects.create(
            employee=employee,
            site=site,
            **defaults,
        )
    else:
        for key, value in defaults.items():
            setattr(enrollment, key, value)
        enrollment.save()
    return enrollment


def unpublish_employee_from_site(employee, site):
    from apps.hr.models import EmployeeWordPressEnrollment

    if not site.is_configured():
        raise WordPressError('WordPress site is missing URL, user, or application password.')
    enrollment = EmployeeWordPressEnrollment.objects.filter(
        employee=employee, site=site,
    ).first()
    if enrollment is None or not (enrollment.posttitle or ''):
        raise WordPressError('No WordPress post is recorded for this employee on this site.')
    try:
        unpublish_wordpress_post(site, enrollment.posttitle)
    except WordPressError as exc:
        enrollment.detail = str(exc)
        enrollment.save(update_fields=['detail', 'updated_at'])
        raise
    enrollment.status = EmployeeWordPressEnrollment.Status.UNPUBLISHED
    enrollment.needs_attention = False
    enrollment.detail = ''
    enrollment.last_synced_at = timezone.now()
    enrollment.save(update_fields=[
        'status', 'needs_attention', 'detail', 'last_synced_at', 'updated_at',
    ])
    return enrollment
