from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render

from .file_service import ThereseFileService
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


@login_required
def global_settings(request):
    from apps.accounts.account_emails import (
        ACCOUNT_EMAIL_VARIABLES,
        ensure_account_email_templates,
        save_account_email_templates_from_post,
    )
    from apps.accounts.permissions import user_can_edit_global_settings
    from apps.core.forms import GlobalSettingForm
    from apps.core.models import GlobalSetting

    if not user_can_edit_global_settings(request.user):
        raise PermissionDenied

    setting = GlobalSetting.get_solo()
    form = GlobalSettingForm(instance=setting)
    from apps.holidays.forms import HolidayCustomDayFormSet
    from apps.holidays.models import HolidayCustomDay, HolidayEntitlementRate
    from apps.holidays.services import ensure_default_rates

    ensure_default_rates()
    custom_qs = HolidayCustomDay.objects.order_by('day')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_account_emails':
            save_account_email_templates_from_post(request.POST)
            messages.success(request, 'Account email templates were saved.')
            return redirect('core_settings:global_settings')
        form = GlobalSettingForm(request.POST, instance=setting)
        custom_formset = HolidayCustomDayFormSet(request.POST, queryset=custom_qs)
        if form.is_valid() and custom_formset.is_valid():
            form.save()
            custom_formset.save()
            for weekdays in range(1, 6):
                for months in range(1, 13):
                    raw = request.POST.get(f'entitlement_{weekdays}_{months}')
                    if raw in (None, ''):
                        continue
                    HolidayEntitlementRate.objects.update_or_create(
                        weekdays=weekdays,
                        contract_months=months,
                        defaults={'days': raw},
                    )
            messages.success(request, 'Global settings were saved.')
            return redirect('core_settings:global_settings')
    else:
        custom_formset = HolidayCustomDayFormSet(queryset=custom_qs)

    rates = {
        (row.weekdays, row.contract_months): row.days
        for row in HolidayEntitlementRate.objects.all()
    }
    entitlement_grid = []
    for weekdays in range(5, 0, -1):
        entitlement_grid.append({
            'weekdays': weekdays,
            'cells': [
                {'months': months, 'value': rates.get((weekdays, months), '')}
                for months in range(12, 0, -1)
            ],
        })
    return render(request, 'core/global_settings.html', {
        'form': form,
        'setting': setting,
        'account_email_templates': ensure_account_email_templates(),
        'account_email_variables': ACCOUNT_EMAIL_VARIABLES,
        'custom_formset': custom_formset,
        'entitlement_grid': entitlement_grid,
        'month_range': range(12, 0, -1),
    })
