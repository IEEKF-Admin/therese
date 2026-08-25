"""
apps/accounts/views.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Custom Login View that redirects to tasks dashboard
- ForcePasswordChangeView that forces first-time users to change password
- All redirects use correct namespace ('tasks:my_tasks')
- All user-facing text in English

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.contrib.auth.views import PasswordChangeView, LoginView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages


class ForcePasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('tasks:my_tasks')   # ← WICHTIG: Namespace hinzugefügt

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Change Password'
        context['subtitle'] = 'You must change your password before you can continue working.'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.password_changed = True
        self.request.user.save(update_fields=['password_changed'])
        messages.success(self.request, 'Password successfully changed. Welcome to THERESE!')
        return response


class ThereseLoginView(LoginView):
    """Custom Login View that always redirects to the tasks dashboard"""
    template_name = 'registration/login.html'
    redirect_authenticated_user = True
    success_url = reverse_lazy('tasks:my_tasks')   # ← Namespace korrigiert


from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone as dj_timezone

from django.contrib.auth.models import Group

from apps.hr.models import Workgroup

from .models import CustomUser, LoginPopupConfig


def _parse_trigger_datetime(dt_value):
    """Parse datetime-local input (naive, local) into an aware datetime."""
    if not dt_value:
        return None
    try:
        naive = datetime.fromisoformat(dt_value.replace('T', ' '))
        return dj_timezone.make_aware(naive, dj_timezone.get_current_timezone())
    except (ValueError, TypeError):
        return None


def _login_popup_config_dict(config):
    trigger_dt = ''
    if config.trigger_datetime:
        trigger_dt = dj_timezone.localtime(config.trigger_datetime).strftime('%Y-%m-%dT%H:%M')
    return {
        'pk': config.pk,
        'name': config.name,
        'trigger': config.trigger,
        'reaction_type': config.reaction_type,
        'show_popup': config.show_popup,
        'send_email': config.send_email,
        'link_to': config.link_to,
        'x_months': config.x_months,
        'trigger_datetime': trigger_dt,
        'text': config.text,
        'email_subject': config.email_subject or '',
        'email_html': config.email_html or '',
        'enabled': config.enabled,
        'audience_match_mode': config.audience_match_mode,
        'target_user_ids': list(config.target_users.values_list('pk', flat=True)),
        'target_workgroup_ids': list(config.target_workgroups.values_list('pk', flat=True)),
        'target_group_ids': list(config.target_groups.values_list('pk', flat=True)),
    }


def _set_popup_audience(config, post_data):
    config.target_users.set(post_data.getlist('target_users'))
    config.target_workgroups.set(post_data.getlist('target_workgroups'))
    config.target_groups.set(post_data.getlist('target_groups'))


def login_popup_settings(request):
    return redirect('core_settings:messaging')


@login_required
def messaging(request):
    from django.core.exceptions import PermissionDenied

    from apps.accounts.permissions import user_can_configure_email, user_can_manage_messaging
    from apps.accounts.template_variables import GROUP_LABELS, VARIABLES, catalog_by_trigger, variable_token
    from apps.core.html_sanitize import sanitize_html
    from apps.core.mail import send_therese_test_email
    from apps.core.views import (
        EMAIL_ENV_VARIABLES,
        TestEmailForm,
        _default_test_recipient,
        _email_environment_status,
    )

    if not user_can_manage_messaging(request.user):
        raise PermissionDenied
    can_configure_email = user_can_configure_email(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'send_test':
            if not can_configure_email:
                raise PermissionDenied
            form = TestEmailForm(request.POST)
            if form.is_valid():
                recipient = form.cleaned_data['recipient']
                try:
                    send_therese_test_email(
                        recipient,
                        requested_by=request.user.get_username(),
                    )
                except Exception as exc:
                    messages.error(request, f'Test email could not be sent: {exc}')
                else:
                    messages.success(
                        request,
                        f'Test email was handed to the mail server for {recipient}.',
                    )
                    return redirect('core_settings:messaging')
            test_form = form
        else:
            test_form = TestEmailForm(initial={'recipient': _default_test_recipient(request.user)})
            if action == 'delete_selected':
                for pk in request.POST.getlist('selected_configs'):
                    try:
                        LoginPopupConfig.objects.get(pk=pk).delete()
                    except LoginPopupConfig.DoesNotExist:
                        pass
                return redirect('core_settings:messaging')

            if request.POST.get('delete_pk'):
                try:
                    LoginPopupConfig.objects.get(pk=request.POST['delete_pk']).delete()
                except LoginPopupConfig.DoesNotExist:
                    pass
                return redirect('core_settings:messaging')

            pk = request.POST.get('pk')
            if pk:
                config = LoginPopupConfig.objects.get(pk=pk)
            else:
                config = LoginPopupConfig()
            config.name = request.POST.get('name', '')
            config.trigger = request.POST.get('trigger', '')
            config.reaction_type = 'popup'
            config.show_popup = bool(request.POST.get('show_popup'))
            config.send_email = bool(request.POST.get('send_email'))
            config.text = request.POST.get('text', '')
            config.email_subject = (request.POST.get('email_subject') or '')[:200]
            config.email_html = sanitize_html(request.POST.get('email_html') or '')
            config.link_to = request.POST.get('link_to', '')
            x = request.POST.get('x_months')
            config.x_months = int(x) if x else None
            config.trigger_datetime = _parse_trigger_datetime(request.POST.get('trigger_datetime'))
            config.enabled = bool(request.POST.get('enabled'))
            match_mode = request.POST.get('audience_match_mode', 'or')
            config.audience_match_mode = match_mode if match_mode in ('or', 'and') else 'or'
            config.save()
            _set_popup_audience(config, request.POST)
            return redirect('core_settings:messaging')
    else:
        test_form = TestEmailForm(initial={'recipient': _default_test_recipient(request.user)})

    configs = (
        LoginPopupConfig.objects.all()
        .prefetch_related('target_users', 'target_workgroups', 'target_groups')
        .order_by('name')
    )
    return render(request, 'accounts/messaging.html', {
        'configs': configs,
        'configs_data': [_login_popup_config_dict(c) for c in configs],
        'trigger_choices': LoginPopupConfig.TRIGGER_CHOICES,
        'link_choices': LoginPopupConfig.LINK_CHOICES,
        'audience_match_choices': LoginPopupConfig.AUDIENCE_MATCH_CHOICES,
        'variable_catalog': catalog_by_trigger(),
        'all_template_variables': [
            {
                **item,
                'token': variable_token(item['key']),
                'group_label': GROUP_LABELS[item['group']],
            }
            for item in VARIABLES
        ],
        'all_users': CustomUser.objects.filter(is_active=True).order_by('last_name', 'first_name', 'username'),
        'all_workgroups': Workgroup.objects.order_by('short_name'),
        'all_groups': Group.objects.order_by('name'),
        'can_configure_email': can_configure_email,
        'smtp_status': _email_environment_status() if can_configure_email else None,
        'smtp_variables': EMAIL_ENV_VARIABLES if can_configure_email else [],
        'form': test_form,
    })


