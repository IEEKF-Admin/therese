"""Random passwords and account notification emails (welcome / reset)."""

from __future__ import annotations

import logging
import random
import secrets
import threading
import time

from django.conf import settings
from django.urls import reverse

from apps.accounts.models import AccountEmailTemplate
from apps.accounts.template_variables import recipient_email, render_placeholders
from apps.core.html_sanitize import sanitize_html
from apps.core.mail import send_therese_html_email

logger = logging.getLogger(__name__)

PASSWORD_ALPHABET = (
    'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
)
PASSWORD_LENGTH = 12

ACCOUNT_EMAIL_VARIABLES = [
    {'key': 'prefix', 'label': 'Prefix / title', 'token': '{{ prefix }}'},
    {'key': 'first_name', 'label': 'First name', 'token': '{{ first_name }}'},
    {'key': 'last_name', 'label': 'Last name', 'token': '{{ last_name }}'},
    {'key': 'login_url', 'label': 'Login URL', 'token': '{{ login_url }}'},
    {'key': 'username', 'label': 'Username', 'token': '{{ username }}'},
    {'key': 'password', 'label': 'Password', 'token': '{{ password }}'},
]

DEFAULT_TEMPLATES = {
    AccountEmailTemplate.KIND_USER_CREATED: {
        'subject': 'Your THERESE account',
        'body_html': (
            '<p>Hello {{ prefix }} {{ first_name }} {{ last_name }},</p>'
            '<p>A login for THERESE has been created for you.</p>'
            '<p>Login URL: {{ login_url }}<br>'
            'Username: {{ username }}<br>'
            'Password: {{ password }}</p>'
            '<p>You will be asked to choose a new password after signing in.</p>'
        ),
    },
    AccountEmailTemplate.KIND_PASSWORD_RESET: {
        'subject': 'Your THERESE password was reset',
        'body_html': (
            '<p>Hello {{ prefix }} {{ first_name }} {{ last_name }},</p>'
            '<p>Your THERESE password has been reset.</p>'
            '<p>Login URL: {{ login_url }}<br>'
            'Username: {{ username }}<br>'
            'Password: {{ password }}</p>'
            '<p>You will be asked to choose a new password after signing in.</p>'
        ),
    },
}


def generate_random_password(length=PASSWORD_LENGTH):
    length = max(8, int(length))
    chars = [secrets.choice(PASSWORD_ALPHABET) for _ in range(length)]
    return ''.join(chars)


def account_login_url():
    path = reverse('accounts:login')
    base = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    if base:
        return base + path
    return path


def ensure_account_email_templates():
    templates = []
    for kind, defaults in DEFAULT_TEMPLATES.items():
        obj, created = AccountEmailTemplate.objects.get_or_create(
            kind=kind,
            defaults={
                'subject': defaults['subject'],
                'body_html': defaults['body_html'],
            },
        )
        if created:
            obj.body_html = sanitize_html(obj.body_html)
            obj.save(update_fields=['body_html'])
        templates.append(obj)
    return templates


def save_account_email_templates_from_post(post, files=None):
    """Update both account email kinds from a POST dict. Returns saved templates."""
    from apps.core.upload_validation import DOC_ATTACHMENT_EXT, IMAGE_EXT, PDF_EXT, validate_upload

    files = files or {}
    ensure_account_email_templates()
    saved = []
    allowed = PDF_EXT | IMAGE_EXT | DOC_ATTACHMENT_EXT
    for kind, _label in AccountEmailTemplate.KIND_CHOICES:
        template = AccountEmailTemplate.objects.filter(kind=kind).first()
        if template is None:
            continue
        template.subject = (post.get(f'subject_{kind}') or '')[:200]
        template.body_html = sanitize_html(post.get(f'body_{kind}') or '')
        update_fields = ['subject', 'body_html']
        uploaded = files.get(f'attachment_{kind}') if hasattr(files, 'get') else None
        if uploaded:
            validate_upload(uploaded, allowed_extensions=allowed, require_magic=False)
            template.attachment = uploaded
            update_fields.append('attachment')
        elif post.get(f'clear_attachment_{kind}'):
            if template.attachment:
                template.attachment.delete(save=False)
            template.attachment = None
            update_fields.append('attachment')
        template.save(update_fields=update_fields)
        saved.append(template)
    return saved


def _employee_of_user(user):
    try:
        return user.employee
    except Exception:
        return None


def build_account_email_replacements(user, employee, password):
    if employee is None:
        employee = _employee_of_user(user)
    prefix = ''
    first = getattr(user, 'first_name', '') or ''
    last = getattr(user, 'last_name', '') or ''
    if employee is not None:
        prefix = getattr(employee, 'prefix', '') or ''
        first = first or (employee.first_name or '')
        last = last or (employee.last_name or '')
    return {
        'prefix': prefix,
        'first_name': first,
        'last_name': last,
        'login_url': account_login_url(),
        'username': getattr(user, 'username', '') or '',
        'password': password or '',
    }


def send_account_email(kind, user, employee, password):
    ensure_account_email_templates()
    template = AccountEmailTemplate.objects.filter(kind=kind).first()
    if template is None or not (template.body_html or '').strip():
        logger.warning('Account email skipped: no template for %s', kind)
        return False
    to_email = recipient_email(user, employee)
    if not to_email:
        logger.warning(
            'Account email skipped for user %s: no recipient',
            getattr(user, 'pk', None),
        )
        return False
    replacements = build_account_email_replacements(user, employee, password)
    subject = render_placeholders(
        template.subject or template.get_kind_display(),
        replacements,
        html=False,
        user=user,
        employee=employee,
    )
    html_body = render_placeholders(
        template.body_html,
        replacements,
        html=True,
        user=user,
        employee=employee,
    )
    attachments = []
    if template.attachment:
        try:
            filename = template.attachment.name.rsplit('/', 1)[-1]
            with template.attachment.open('rb') as fh:
                content = fh.read()
            attachments.append((filename, content))
        except Exception:
            logger.exception('Account email attachment could not be read for %s', kind)
    try:
        send_therese_html_email(
            to_email, subject, html_body, attachments=attachments or None,
        )
    except Exception:
        logger.exception('Account email failed for user %s kind %s', user.pk, kind)
        return False
    return True


def set_random_password(user):
    password = generate_random_password()
    user.set_password(password)
    user.password_changed = False
    user.save(update_fields=['password', 'password_changed'])
    return password


def reset_and_notify(user, employee=None, *, kind=AccountEmailTemplate.KIND_PASSWORD_RESET):
    password = set_random_password(user)
    sent = send_account_email(kind, user, employee, password)
    return password, sent


def _pause_seconds():
    lo = float(getattr(settings, 'ACCOUNT_EMAIL_PAUSE_MIN', 5) or 0)
    hi = float(getattr(settings, 'ACCOUNT_EMAIL_PAUSE_MAX', 15) or 0)
    if hi <= 0:
        return 0
    if hi < lo:
        hi = lo
    return random.uniform(lo, hi)


def send_account_emails_with_pause(jobs):
    """jobs: list of dicts kind, user, employee, password.

    Several messages are spaced by a random pause so the SMTP host is not flooded.
    """
    if not jobs:
        return

    def _run():
        for index, job in enumerate(jobs):
            if index > 0:
                delay = _pause_seconds()
                if delay:
                    time.sleep(delay)
            try:
                send_account_email(
                    job['kind'],
                    job['user'],
                    job.get('employee'),
                    job['password'],
                )
            except Exception:
                logger.exception('Queued account email failed')

    pause = _pause_seconds()
    if pause > 0 and len(jobs) > 1:
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()


def reset_passwords_for_employees(employees):
    """Reset passwords for employees that have a login user. Returns counts."""
    jobs = []
    skipped = 0
    for employee in employees:
        user = getattr(employee, 'user', None)
        if user is None:
            skipped += 1
            continue
        password = set_random_password(user)
        jobs.append({
            'kind': AccountEmailTemplate.KIND_PASSWORD_RESET,
            'user': user,
            'employee': employee,
            'password': password,
        })
    send_account_emails_with_pause(jobs)
    return len(jobs), skipped
