"""Outbound mail helpers. SMTP comes from Global Settings; non-empty EMAIL_HOST in .env wins."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection, send_mail
from django.utils.html import strip_tags


def _env_host() -> str:
    return (getattr(settings, 'EMAIL_HOST', '') or '').strip()


def mail_params(setting=None) -> dict:
    """Effective SMTP settings. A non-empty EMAIL_HOST in .env overrides the database."""
    if _env_host():
        password = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
        return {
            'host': _env_host(),
            'port': int(getattr(settings, 'EMAIL_PORT', 465) or 465),
            'username': (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip(),
            'password': password,
            'use_ssl': bool(getattr(settings, 'EMAIL_USE_SSL', False)),
            'use_tls': bool(getattr(settings, 'EMAIL_USE_TLS', False)),
            'from_email': (
                (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip()
                or (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip()
            ),
            'source': 'env',
        }
    if setting is None:
        from apps.core.models import GlobalSetting

        setting = GlobalSetting.get_solo()
    username = (getattr(setting, 'smtp_user', '') or '').strip()
    from_email = (getattr(setting, 'smtp_from_email', '') or '').strip() or username
    return {
        'host': (getattr(setting, 'smtp_host', '') or '').strip(),
        'port': int(getattr(setting, 'smtp_port', 465) or 465),
        'username': username,
        'password': getattr(setting, 'smtp_password', '') or '',
        'use_ssl': bool(getattr(setting, 'smtp_use_ssl', True)),
        'use_tls': bool(getattr(setting, 'smtp_use_tls', False)),
        'from_email': from_email,
        'source': 'db',
    }


def mail_configured(setting=None) -> bool:
    params = mail_params(setting)
    return bool(params['from_email'])


def get_from_email(setting=None) -> str:
    return mail_params(setting)['from_email']


def get_mail_connection(setting=None):
    backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').strip()
    if backend and 'smtp.EmailBackend' not in backend:
        return get_connection(backend)
    params = mail_params(setting)
    if not params['host']:
        return get_connection('django.core.mail.backends.console.EmailBackend')
    return get_connection(
        'django.core.mail.backends.smtp.EmailBackend',
        host=params['host'],
        port=params['port'],
        username=params['username'] or None,
        password=params['password'] or None,
        use_tls=params['use_tls'],
        use_ssl=params['use_ssl'],
    )


def send_therese_test_email(to_email, *, requested_by=''):
    """Send a single test message so operators can verify SMTP settings."""
    from_email = get_from_email() or None
    send_mail(
        subject='THERESE email test',
        message=(
            'This is a test message from THERESE.\n\n'
            f'Sent by: {requested_by or "unknown"}\n'
            f'From: {from_email or "Django default"}\n'
        ),
        from_email=from_email,
        recipient_list=[to_email],
        fail_silently=False,
        connection=get_mail_connection(),
    )


def send_therese_html_email(to_email, subject, html_body, *, fail_silently=False, attachments=None):
    """Send an HTML message with a plain-text fallback."""
    from_email = get_from_email() or None
    text = strip_tags(html_body or '')
    message = EmailMultiAlternatives(
        subject=subject or '',
        body=text,
        from_email=from_email,
        to=[to_email],
        connection=get_mail_connection(),
    )
    message.attach_alternative(html_body or '', 'text/html')
    for item in attachments or []:
        if not item:
            continue
        if len(item) == 3:
            message.attach(item[0], item[1], item[2])
        else:
            message.attach(*item)
    message.send(fail_silently=fail_silently)
