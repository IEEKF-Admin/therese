from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import LoginPopupConfig
from apps.accounts.template_variables import (
    GROUP_LABELS,
    VARIABLES,
    catalog_by_trigger,
    variable_token,
)
from apps.core.html_sanitize import sanitize_html

from .file_service import ThereseFileService
from .mail import send_therese_test_email
from .media_access import user_can_access_stored_file


class TestEmailForm(forms.Form):
    recipient = forms.EmailField(
        label='Send test email to',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.org'}),
    )

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


def _email_environment_status():
    password = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
    return {
        'backend': getattr(settings, 'EMAIL_BACKEND', ''),
        'host': getattr(settings, 'EMAIL_HOST', '') or '—',
        'port': getattr(settings, 'EMAIL_PORT', ''),
        'use_ssl': bool(getattr(settings, 'EMAIL_USE_SSL', False)),
        'use_tls': bool(getattr(settings, 'EMAIL_USE_TLS', False)),
        'host_user': getattr(settings, 'EMAIL_HOST_USER', '') or '—',
        'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '—',
        'password_configured': bool(str(password).strip()),
    }


def _default_test_recipient(user):
    email = (getattr(user, 'email', '') or '').strip()
    if email:
        return email
    employee = getattr(user, 'employee', None)
    if employee is not None:
        return (getattr(employee, 'email_professional', '') or '').strip()
    return ''


def _save_trigger_email_template(request):
    config = get_object_or_404(LoginPopupConfig, pk=request.POST.get('config_pk'))
    config.send_email = bool(request.POST.get('send_email'))
    config.email_subject = (request.POST.get('email_subject') or '')[:200]
    config.email_html = sanitize_html(request.POST.get('email_html') or '')
    config.save(update_fields=['send_email', 'email_subject', 'email_html', 'updated_at'])
    messages.success(request, f'Email template for “{config.name}” was saved.')
    return redirect('core_settings:email_environment')


@login_required
@permission_required('core.configure_email', raise_exception=True)
def email_environment(request):
    """Describe .env email settings without exposing secrets. Allow a test send."""
    action = request.POST.get('action') or 'send_test'
    if request.method == 'POST' and action == 'save_template':
        return _save_trigger_email_template(request)

    form = TestEmailForm(
        request.POST or None if request.method == 'POST' and action == 'send_test' else None,
        initial={'recipient': _default_test_recipient(request.user)},
    )
    if request.method == 'POST' and action == 'send_test':
        if form.is_valid():
            recipient = form.cleaned_data['recipient']
            try:
                send_therese_test_email(
                    recipient,
                    requested_by=request.user.get_username(),
                )
            except Exception as exc:
                messages.error(
                    request,
                    f'Test email could not be sent: {exc}',
                )
            else:
                messages.success(
                    request,
                    f'Test email was handed to the mail server for {recipient}.',
                )
                return redirect('core_settings:email_environment')
    trigger_configs = LoginPopupConfig.objects.order_by('name')
    return render(request, 'core/email_environment.html', {
        'variables': EMAIL_ENV_VARIABLES,
        'status': _email_environment_status(),
        'form': form,
        'trigger_configs': trigger_configs,
        'variable_catalog': catalog_by_trigger(),
        'all_template_variables': [
            {
                **item,
                'token': variable_token(item['key']),
                'group_label': GROUP_LABELS[item['group']],
            }
            for item in VARIABLES
        ],
    })
