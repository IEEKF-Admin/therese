from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404
from django.shortcuts import render

from .file_service import ThereseFileService
from .media_access import user_can_access_stored_file

EMAIL_ENV_VARIABLES = [
    {
        'name': 'EMAIL_BACKEND',
        'example': 'django.core.mail.backends.smtp.EmailBackend',
        'description': (
            'Django mail backend. Use the SMTP backend in production. '
            'Leave EMAIL_HOST empty to print messages to the server log instead.'
        ),
    },
    {
        'name': 'EMAIL_HOST',
        'example': 'smtp.strato.de',
        'description': 'SMTP hostname of the institute mailbox provider.',
    },
    {
        'name': 'EMAIL_PORT',
        'example': '465',
        'description': 'SMTP port. Strato documents 465 with SSL/TLS.',
    },
    {
        'name': 'EMAIL_USE_SSL',
        'example': 'True',
        'description': 'Use implicit TLS (typical for port 465). Mutually exclusive with EMAIL_USE_TLS.',
    },
    {
        'name': 'EMAIL_USE_TLS',
        'example': 'False',
        'description': 'Use STARTTLS (typical for port 587). Keep False when EMAIL_USE_SSL is True.',
    },
    {
        'name': 'EMAIL_HOST_USER',
        'example': 'noreply@example.org',
        'description': 'SMTP username. For Strato this is the full mailbox address.',
    },
    {
        'name': 'EMAIL_HOST_PASSWORD',
        'example': '(set only in the local .env file, never in git)',
        'description': 'SMTP password. Stored only in .env on the server. Never shown in this UI.',
    },
    {
        'name': 'DEFAULT_FROM_EMAIL',
        'example': 'noreply@example.org',
        'description': 'From address used by THERESE. Should match the SMTP mailbox.',
    },
    {
        'name': 'SERVER_EMAIL',
        'example': 'noreply@example.org',
        'description': 'Optional. Address for error mails from the server. Defaults to DEFAULT_FROM_EMAIL.',
    },
]


@login_required
def serve_stored_file(request, file_path):
    if not ThereseFileService.exists(file_path):
        raise Http404('File not found.')
    if not user_can_access_stored_file(request.user, file_path):
        raise Http404('File not found.')
    # Default to attachment; allow inline only for known-safe image/PDF types.
    return ThereseFileService.as_response(file_path, allow_inline=True)


@login_required
@permission_required('core.configure_email', raise_exception=True)
def email_environment(request):
    """Describe .env email settings without exposing secrets."""
    password = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
    status = {
        'backend': getattr(settings, 'EMAIL_BACKEND', ''),
        'host': getattr(settings, 'EMAIL_HOST', '') or '—',
        'port': getattr(settings, 'EMAIL_PORT', ''),
        'use_ssl': bool(getattr(settings, 'EMAIL_USE_SSL', False)),
        'use_tls': bool(getattr(settings, 'EMAIL_USE_TLS', False)),
        'host_user': getattr(settings, 'EMAIL_HOST_USER', '') or '—',
        'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '—',
        'password_configured': bool(str(password).strip()),
    }
    return render(request, 'core/email_environment.html', {
        'variables': EMAIL_ENV_VARIABLES,
        'status': status,
    })
