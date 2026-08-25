"""Outbound mail helpers. SMTP credentials stay in .env / Django settings."""

from django.conf import settings
from django.core.mail import send_mail


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
