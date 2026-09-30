from datetime import date

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

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
        'description': (
            'SMTP hostname. A non-empty value overrides SMTP in '
            'Global Settings → Integrations.'
        ),
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
    from apps.core.mail import mail_params

    params = mail_params()
    return {
        'backend': getattr(settings, 'EMAIL_BACKEND', ''),
        'host': params['host'] or '—',
        'port': params['port'],
        'use_ssl': params['use_ssl'],
        'use_tls': params['use_tls'],
        'host_user': params['username'] or '—',
        'from_email': params['from_email'] or '—',
        'password_configured': bool(str(params['password']).strip()),
        'source': params['source'],
    }


def _default_test_recipient(user):
    email = (getattr(user, 'email', '') or '').strip()
    if email:
        return email
    employee = getattr(user, 'employee', None)
    if employee is not None:
        return (getattr(employee, 'email_professional', '') or '').strip()
    return ''


def _payscale_instances():
    from apps.finances.models import PayScale
    return PayScale.display_instances()


@login_required
def global_settings(request):
    from apps.accounts.account_emails import (
        ACCOUNT_EMAIL_VARIABLES,
        ensure_account_email_templates,
        save_account_email_templates_from_post,
    )
    from apps.accounts.permissions import user_can_edit_global_settings, user_is_hr_superassistant
    from apps.core.forms import (
        GlobalSettingForm,
        SETTINGS_TAB_ACTIONS,
        global_setting_form_class,
    )
    from apps.core.models import GlobalSetting
    from apps.core.occupation_salary import occupation_tables_for_settings
    from django.db.models import Count
    from apps.inventory.models import InventoryItemType
    from apps.tasks.views.workflow_admin import workflow_config_list_rows

    can_edit_global = user_can_edit_global_settings(request.user)
    can_manage_workflow = user_is_hr_superassistant(request.user) or can_edit_global
    if not can_edit_global and not can_manage_workflow:
        raise PermissionDenied

    setting = GlobalSetting.get_solo()
    form = GlobalSettingForm(instance=setting)
    from apps.holidays.forms import HolidayCustomDayFormSet
    from apps.holidays.models import HolidayCustomDay, HolidayEntitlementRate
    from apps.holidays.services import ensure_default_rates

    ensure_default_rates()
    custom_qs = HolidayCustomDay.objects.order_by('day')

    posted_tab = ''
    settings_url = reverse('core_settings:global_settings')
    if request.method == 'POST':
        if not can_edit_global:
            raise PermissionDenied
        action = request.POST.get('action')
        if action == 'save_account_emails':
            save_account_email_templates_from_post(request.POST, request.FILES)
            messages.success(request, 'Account email templates were saved.')
            return redirect(settings_url + '?tab=emails')
        tab = SETTINGS_TAB_ACTIONS.get(action)
        if tab:
            posted_tab = tab
            TabForm = global_setting_form_class(tab)
            tab_form = TabForm(request.POST, instance=setting)
            if tab == 'holidays':
                custom_formset = HolidayCustomDayFormSet(request.POST, queryset=custom_qs)
            else:
                custom_formset = HolidayCustomDayFormSet(queryset=custom_qs)
            holidays_ok = tab != 'holidays' or custom_formset.is_valid()
            if tab_form.is_valid() and holidays_ok:
                tab_form.save()
                if tab == 'holidays':
                    custom_formset.save()
                    for weekdays in range(1, 6):
                        for months in range(1, 13):
                            raw = request.POST.get(f'entitlement_{weekdays}_{months}')
                            if raw in (None, ''):
                                continue
                            from decimal import Decimal, InvalidOperation
                            from apps.tasks.form_validation import parse_loose_decimal

                            try:
                                days = Decimal(str(parse_loose_decimal(raw)))
                            except (InvalidOperation, ValueError, TypeError):
                                continue
                            HolidayEntitlementRate.objects.update_or_create(
                                weekdays=weekdays,
                                contract_months=months,
                                defaults={'days': days},
                            )
                elif tab == 'personnel':
                    from apps.core.occupation_salary import save_occupation_tables_from_post
                    save_occupation_tables_from_post(request.POST)
                elif tab == 'inventory':
                    from apps.inventory.services import save_inventory_types_from_post
                    save_inventory_types_from_post(request.POST)
                elif tab == 'integrations':
                    _save_workgroup_sympa_lists(request.POST)
                    _save_wordpress_sites(request.POST)
                messages.success(request, 'Global settings were saved.')
                return redirect(settings_url + f'?tab={tab}')
            for name in tab_form.fields:
                form.initial[name] = tab_form[name].value()
            form._errors = tab_form.errors
        else:
            custom_formset = HolidayCustomDayFormSet(queryset=custom_qs)
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
    requested_tab = posted_tab or (request.GET.get('tab') or '').strip()
    allowed_tabs = {
        'general', 'personnel', 'chemicals', 'inventory', 'holidays', 'emails',
        'integrations',
    }
    if requested_tab == 'workflow' and can_manage_workflow:
        settings_default_tab = 'workflow'
    elif can_edit_global and requested_tab in allowed_tabs:
        settings_default_tab = requested_tab
    elif can_edit_global:
        settings_default_tab = 'general'
    else:
        settings_default_tab = 'workflow'
    from apps.holidays.mail import HOLIDAY_EMAIL_VARIABLES
    from apps.core.google_calendar import service_account_configured, service_account_email
    from apps.core.mail import mail_params
    from apps.hr.models import Workgroup

    smtp = mail_params(setting)
    return render(request, 'core/global_settings.html', {
        'form': form,
        'setting': setting,
        'occupation_tables': occupation_tables_for_settings(),
        'payscale_instances': _payscale_instances(),
        'occupation_today': date.today().isoformat(),
        'inventory_types': InventoryItemType.objects.annotate(
            item_count=Count('items'),
        ).order_by('name'),
        'account_email_templates': ensure_account_email_templates(),
        'account_email_variables': ACCOUNT_EMAIL_VARIABLES,
        'holiday_email_variables': HOLIDAY_EMAIL_VARIABLES,
        'custom_formset': custom_formset,
        'entitlement_grid': entitlement_grid,
        'month_range': range(12, 0, -1),
        'can_edit_global': can_edit_global,
        'can_manage_workflow': can_manage_workflow,
        'workflow_rows': workflow_config_list_rows() if can_manage_workflow else [],
        'settings_default_tab': settings_default_tab,
        'google_service_account_configured': service_account_configured(setting),
        'google_service_account_email': service_account_email(setting),
        'smtp_env_override': smtp['source'] == 'env',
        'smtp_password_configured': bool((setting.smtp_password or '').strip()),
        'workgroups': Workgroup.objects.order_by('short_name'),
        'wordpress_sites': _wordpress_site_rows(),
    })


def _save_workgroup_sympa_lists(post):
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    from apps.hr.models import Workgroup

    for workgroup in Workgroup.objects.all():
        raw = (post.get(f'sympa_wg_{workgroup.pk}') or '').strip()
        if raw:
            try:
                validate_email(raw)
            except ValidationError:
                continue
        if (workgroup.sympa_list or '') == raw:
            continue
        workgroup.sympa_list = raw
        workgroup.save(update_fields=['sympa_list'])


def _wordpress_site_rows():
    from apps.hr.models import WordPressSite

    rows = list(WordPressSite.objects.prefetch_related('workgroups').order_by('name'))
    return rows


def _save_wordpress_sites(post):
    if post.get('wp_sites_present') != '1':
        return
    from apps.hr.models import WordPressSite, Workgroup

    keep_ids = set()
    index = 0
    while True:
        prefix = f'wp_site_{index}_'
        if f'{prefix}name' not in post and f'{prefix}id' not in post:
            break
        index += 1
        if post.get(f'{prefix}delete') in ('1', 'on', 'true'):
            pk = post.get(f'{prefix}id')
            if pk and str(pk).isdigit():
                WordPressSite.objects.filter(pk=int(pk)).delete()
            continue
        name = (post.get(f'{prefix}name') or '').strip()
        url = (post.get(f'{prefix}url') or '').strip().rstrip('/')
        username = (post.get(f'{prefix}username') or '').strip()
        password = post.get(f'{prefix}password')
        if password is None:
            password = ''
        wg_ids = []
        for raw in post.getlist(f'{prefix}workgroups'):
            if str(raw).isdigit():
                wg_ids.append(int(raw))
        pk = post.get(f'{prefix}id')
        row = None
        if pk and str(pk).isdigit():
            row = WordPressSite.objects.filter(pk=int(pk)).first()
        if not name and not url:
            if row is not None:
                keep_ids.add(row.pk)
            continue
        if not name:
            name = url or 'WordPress'
        if url and not url.lower().startswith('https://'):
            if row is not None:
                keep_ids.add(row.pk)
            continue
        if row is None:
            row = WordPressSite(name=name, url=url, username=username)
            if password:
                row.application_password = password
            row.save()
        else:
            row.name = name
            row.url = url
            row.username = username
            if (password or '').strip():
                row.application_password = password.strip()
            row.save()
        row.workgroups.set(Workgroup.objects.filter(pk__in=wg_ids))
        keep_ids.add(row.pk)
    WordPressSite.objects.exclude(pk__in=keep_ids).delete()
