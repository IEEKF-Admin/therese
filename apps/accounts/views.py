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

from django.shortcuts import render, redirect
from django.utils import timezone as dj_timezone

from .models import LoginPopupConfig


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
        'link_to': config.link_to,
        'x_months': config.x_months,
        'trigger_datetime': trigger_dt,
        'text': config.text,
        'enabled': config.enabled,
    }


def login_popup_settings(request):
    if not (request.user.is_superuser or request.user.groups.filter(name='Assisting Admins').exists()):
        return redirect('tasks:my_tasks')
    if request.method == 'POST':
        if request.POST.get('action') == 'delete_selected':
            for pk in request.POST.getlist('selected_configs'):
                try:
                    LoginPopupConfig.objects.get(pk=pk).delete()
                except:
                    pass
            return redirect('accounts:login_popup_settings')

        if request.POST.get('delete_pk'):
            try:
                LoginPopupConfig.objects.get(pk=request.POST['delete_pk']).delete()
            except:
                pass
            return redirect('accounts:login_popup_settings')

        pk = request.POST.get('pk')
        if pk:
            config = LoginPopupConfig.objects.get(pk=pk)
        else:
            config = LoginPopupConfig()
        config.name = request.POST.get('name', '')
        config.trigger = request.POST.get('trigger', '')
        config.reaction_type = request.POST.get('reaction_type', 'popup')
        config.text = request.POST.get('text', '')
        config.link_to = request.POST.get('link_to', '')
        x = request.POST.get('x_months')
        config.x_months = int(x) if x else None
        config.trigger_datetime = _parse_trigger_datetime(request.POST.get('trigger_datetime'))
        config.enabled = bool(request.POST.get('enabled'))
        config.save()
        return redirect('accounts:login_popup_settings')

    configs = LoginPopupConfig.objects.all().order_by('name')
    placeholders = [
        '{{ first_name }}',
        '{{ last_name }}',
        '{{ full_name }}',
        '{{ employee_number }}',
        '{{ contract_end }}',
        '{{ today }}',
        '{{ title }}',
    ]

    configs_data = [_login_popup_config_dict(c) for c in configs]

    return render(request, 'accounts/login_popup_settings.html', {
        'configs': configs,
        'configs_data': configs_data,
        'trigger_choices': LoginPopupConfig.TRIGGER_CHOICES,
        'reaction_choices': LoginPopupConfig.REACTION_CHOICES,
        'link_choices': LoginPopupConfig.LINK_CHOICES,
        'placeholders': placeholders,
    })


