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
    success_url = reverse_lazy('tasks:my_tasks')   # â† WICHTIG: Namespace hinzugefÃ¼gt

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
    success_url = reverse_lazy('tasks:my_tasks')   # â† Namespace korrigiert


