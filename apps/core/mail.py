"""Outbound mail helpers. SMTP comes from Global Settings only."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection, send_mail
from django.utils.html import strip_tags


def smtp_security(port, use_ssl, use_tls) -> tuple[bool, bool]:
    """Implicit SSL on 587/25 yields SSL WRONG_VERSION_NUMBER; match flags to the port."""
    try:
        port = int(port or 0)
    except (TypeError, ValueError):
        port = 0
    use_ssl = bool(use_ssl)
    use_tls = bool(use_tls)
    if port == 465:
        return True, False
    if port in (25, 587):
        return False, True
    if use_ssl and use_tls:
        return True, False
    return use_ssl, use_tls


def mail_params(setting=None) -> dict:
    """Effective SMTP settings from Global Settings."""
    if setting is None:
        from apps.core.models import GlobalSetting

        setting = GlobalSetting.get_solo()
    username = (getattr(setting, 'smtp_user', '') or '').strip()
    from_email = (getattr(setting, 'smtp_from_email', '') or '').strip() or username
    port = int(getattr(setting, 'smtp_port', 465) or 465)
    use_ssl, use_tls = smtp_security(
        port,
        getattr(setting, 'smtp_use_ssl', True),
        getattr(setting, 'smtp_use_tls', False),
    )
    return {
        'host': (getattr(setting, 'smtp_host', '') or '').strip(),
        'port': port,
        'username': username,
        'password': getattr(setting, 'smtp_password', '') or '',
        'use_ssl': use_ssl,
        'use_tls': use_tls,
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
