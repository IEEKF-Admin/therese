"""Read-only import of existing Calendar, WordPress, and Sympa enrollments."""

from __future__ import annotations

import re
from collections import Counter

from django.utils import timezone

from apps.core.google_calendar import get_calendar_client, service_account_email
from apps.core.models import GlobalSetting
from apps.core.sympa import list_name, normalize_list_address
from apps.core.wordpress import WordPressError, list_wordpress_posts
from apps.hr.models import Employee, EmployeeExternalAccount, EmployeeWordPressEnrollment, Workgroup
from apps.hr.provisioning import _account, _mark, normalize_google_email
from apps.hr.wordpress import configured_sites, employee_assigned_to_site, source_payload

EMAIL_RE = re.compile(r'[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}', re.I)


def known_sympa_lists() -> list[dict]:
    setting = GlobalSetting.get_solo()
    items: list[dict] = []
    seen: set[str] = set()

    def _add(address: str):
        value = normalize_list_address(address)
        if not value or value in seen:
            return
        seen.add(value)
        items.append({
            'address': value,
            'label': list_name(value) or value,
        })

    _add(setting.sympa_institute_list)
    for workgroup in Workgroup.objects.exclude(sympa_list='').order_by('short_name'):
        _add(workgroup.sympa_list)
    return items


def parse_csv_emails(content) -> list[str]:
    if content is None:
        return []
    if isinstance(content, bytes):
        text = content.decode('utf-8-sig', errors='replace')
    else:
        text = str(content)
    emails: list[str] = []
    seen: set[str] = set()
    for match in EMAIL_RE.finditer(text):
        email = match.group(0).lower()
        if email in seen:
            continue
        seen.add(email)
        emails.append(email)
    return emails


def import_google_calendar(*, client=None) -> dict:
    setting = GlobalSetting.get_solo()
    calendar = client or get_calendar_client(setting)
    remote = set()
    sa = normalize_google_email(service_account_email(setting))
    for raw in calendar.list_shared_emails() or []:
        email = normalize_google_email(raw)
        if not email or email == sa:
            continue
        remote.add(email)

    employees = list(
        Employee.objects.visible().exclude(google_account='').prefetch_related(
            'external_accounts',
        )
    )
    matched = 0
    matched_emails: set[str] = set()
    for employee in employees:
        email = normalize_google_email(employee.google_account)
        if email not in remote:
            continue
        matched_emails.add(email)
        account = _account(employee, EmployeeExternalAccount.Kind.GOOGLE_CALENDAR)
        _mark(account, status=EmployeeExternalAccount.Status.ACTIVE, identifier=email, detail='')
        matched += 1
    return {
        'matched': matched,
        'unmatched': len(remote - matched_emails),
        'errors': 0,
    }


def import_wordpress_sites(*, list_posts=None) -> dict:
    fetch = list_posts or list_wordpress_posts
    sites = [site for site in configured_sites() if site.is_configured()]
    if not sites:
        return {'matched': 0, 'unmatched': 0, 'errors': 0, 'empty': True}

    employees = list(
        Employee.objects.visible().select_related('room__building').prefetch_related(
            'workgroups',
            'wordpress_enrollments',
        )
    )
    matched = unmatched = errors = 0
    error_messages: list[str] = []
    for site in sites:
        try:
            posts = fetch(site) or []
        except WordPressError as exc:
            errors += 1
            error_messages.append(f'{site.name}: {exc}')
            continue
        result = _import_site_posts(site, posts, employees)
        matched += result['matched']
        unmatched += result['unmatched']
    return {
        'matched': matched,
        'unmatched': unmatched,
        'errors': errors,
        'error_messages': error_messages,
        'empty': False,
    }


def _published_posts(posts) -> list[dict]:
    published = []
    for item in posts or []:
        if not isinstance(item, dict):
            continue
        if not item.get('published'):
            continue
        published.append(item)
    return published


def _import_site_posts(site, posts, employees) -> dict:
    published = _published_posts(posts)
    by_title: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}
    for post in published:
        title = (post.get('posttitle') or '').strip()
        name = (post.get('name') or '').strip()
        if title:
            by_title.setdefault(title, []).append(post)
        if name:
            by_name.setdefault(name.casefold(), []).append(post)

    sources = {employee.pk: source_payload(employee) for employee in employees}
    name_counts = Counter(
        (sources[employee.pk].get('name') or '').strip().casefold()
        for employee in employees
        if (sources[employee.pk].get('name') or '').strip()
    )

    used: set[str] = set()
    matched = 0
    for employee in employees:
        source = sources[employee.pk]
        post = None
        title = (source.get('posttitle') or '').strip()
        if title and len(by_title.get(title, [])) == 1:
            post = by_title[title][0]
        else:
            name = (source.get('name') or '').strip()
            key = name.casefold()
            if name and name_counts.get(key) == 1 and len(by_name.get(key, [])) == 1:
                post = by_name[key][0]
        if post is None:
            continue
        post_key = (post.get('posttitle') or '').strip() or f'anon:{id(post)}'
        if post_key in used:
            continue
        used.add(post_key)
        _mark_wordpress_import(employee, site, post, source)
        matched += 1

    unmatched = 0
    for post in published:
        key = (post.get('posttitle') or '').strip() or f'anon:{id(post)}'
        if key not in used:
            unmatched += 1
    return {'matched': matched, 'unmatched': unmatched}


def _mark_wordpress_import(employee, site, post, source) -> None:
    posttitle = (post.get('posttitle') or source.get('posttitle') or '').strip()
    leftover = not employee_assigned_to_site(employee, site)
    now = timezone.now()
    enrollment = None
    cached = getattr(employee, '_prefetched_objects_cache', {}).get('wordpress_enrollments')
    if cached is not None:
        for row in cached:
            if row.site_id == site.pk:
                enrollment = row
                break
    else:
        enrollment = EmployeeWordPressEnrollment.objects.filter(
            employee=employee, site=site,
        ).first()

    fields = {
        'posttitle': posttitle,
        'status': EmployeeWordPressEnrollment.Status.PUBLISHED,
        'last_source': source,
        'detail': '',
        'needs_attention': leftover,
        'last_synced_at': now,
    }
    if enrollment is None:
        EmployeeWordPressEnrollment.objects.create(
            employee=employee,
            site=site,
            **fields,
        )
        return
    for key, value in fields.items():
        setattr(enrollment, key, value)
    enrollment.save(update_fields=[
        'posttitle', 'status', 'last_source', 'detail',
        'needs_attention', 'last_synced_at', 'updated_at',
    ])


def import_sympa_csv(list_address: str, content) -> dict:
    address = normalize_list_address(list_address)
    if not address:
        raise ValueError('Select a mailing list.')
    known = {item['address'] for item in known_sympa_lists()}
    if address not in known:
        raise ValueError('Unknown mailing list.')
    emails = set(parse_csv_emails(content))
    emails.discard(address)
    employees = list(
        Employee.objects.visible().exclude(email_professional='').prefetch_related(
            'external_accounts',
        )
    )
    matched = 0
    matched_emails: set[str] = set()
    for employee in employees:
        email = normalize_google_email(employee.email_professional)
        if email not in emails:
            continue
        matched_emails.add(email)
        account = _account(employee, EmployeeExternalAccount.Kind.SYMPA)
        lists = []
        seen: set[str] = set()
        for item in list(account.lists or []):
            value = normalize_list_address(item)
            if not value or value in seen:
                continue
            seen.add(value)
            lists.append(value)
        if address not in seen:
            lists.append(address)
        _mark(
            account,
            status=EmployeeExternalAccount.Status.ACTIVE,
            identifier=email,
            detail='',
            lists=lists,
        )
        matched += 1
    return {
        'matched': matched,
        'unmatched': len(emails - matched_emails),
        'errors': 0,
    }
