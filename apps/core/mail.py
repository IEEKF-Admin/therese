"""Outbound mail helpers. SMTP credentials stay in .env / Django settings."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.utils.html import strip_tags


def send_therese_test_email(to_email, *, requested_by=''):
    """Send a single test message so operators can verify SMTP settings."""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or None
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
    )


def send_therese_html_email(to_email, subject, html_body, *, fail_silently=False):
    """Send an HTML message with a plain-text fallback."""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or None
    text = strip_tags(html_body or '')
    message = EmailMultiAlternatives(
        subject=subject or '',
        body=text,
        from_email=from_email,
        to=[to_email],
    )
    message.attach_alternative(html_body or '', 'text/html')
    message.send(fail_silently=fail_silently)
