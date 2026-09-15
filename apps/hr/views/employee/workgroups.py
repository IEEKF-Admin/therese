"""
Workgroup management views for assisting admins.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from django.views.generic.edit import DeleteView

from ...extern import workgroup_is_extern
from ...forms import WorkgroupForm
from ...models import Workgroup


def _delete_workgroups_by_ids(ids):
    deleted = 0
    protected = 0
    system_blocked = 0
    for pk in ids:
        try:
            wg = Workgroup.objects.get(pk=pk)
            if workgroup_is_extern(wg):
                system_blocked += 1
                continue
            wg.delete()
            deleted += 1
        except Workgroup.DoesNotExist:
            pass
        except ProtectedError:
            protected += 1
    return deleted, protected, system_blocked


def _workgroup_delete_messages(request, deleted, protected, system_blocked):
    if deleted:
        messages.success(request, f"{deleted} working group(s) deleted.")
    if protected:
        messages.error(request, f"{protected} working group(s) could not be deleted (dependencies exist).")
    if system_blocked:
        messages.error(
            request,
            f'{system_blocked} working group(s) are required and cannot be deleted.',
        )


def add_workgroup_validation_errors(form, exc):
    if hasattr(exc, 'error_dict'):
        for field, errors in exc.error_dict.items():
            for error in errors:
                form.add_error(field if field != '__all__' else None, error)
    elif hasattr(exc, 'messages'):
        for message in exc.messages:
            form.add_error('short_name', message)
    else:
        form.add_error('short_name', exc)


class WorkgroupListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Workgroup
    template_name = 'hr/workgroup_list.html'
    context_object_name = 'workgroups'

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete_selected':
            ids = [i for i in request.POST.getlist('selected_ids') if i]
            if not ids:
                messages.warning(request, "No entries selected.")
                return redirect('hr:workgroup_list')

            deleted, protected, system_blocked = _delete_workgroups_by_ids(ids)
            _workgroup_delete_messages(request, deleted, protected, system_blocked)
            return redirect('hr:workgroup_list')
        return super().post(request, *args, **kwargs)


class WorkgroupCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Workgroup
    form_class = WorkgroupForm
    template_name = 'hr/workgroup_form.html'
    success_url = reverse_lazy('hr:workgroup_list')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ValidationError as exc:
            add_workgroup_validation_errors(form, exc)
            return self.form_invalid(form)


class WorkgroupUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Workgroup
    form_class = WorkgroupForm
    template_name = 'hr/workgroup_form.html'
    success_url = reverse_lazy('hr:workgroup_list')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ValidationError as exc:
            add_workgroup_validation_errors(form, exc)
            return self.form_invalid(form)


class WorkgroupDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Workgroup
    template_name = 'hr/workgroup_confirm_delete.html'
    success_url = reverse_lazy('hr:workgroup_list')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')

    def form_valid(self, form):
        obj = self.object or self.get_object()
        name = obj.short_name
        if workgroup_is_extern(obj):
            messages.error(
                self.request,
                f'Working group "{name}" is required and cannot be deleted.',
            )
            return redirect(self.success_url)
        try:
            response = super().form_valid(form)
            messages.success(self.request, f'Working group "{name}" was deleted.')
            return response
        except ProtectedError:
            messages.error(
                self.request,
                f'Working group "{name}" cannot be deleted because dependencies still exist '
                '(e.g. PI assignment or members).',
            )
            return redirect(self.success_url)

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        name = obj.short_name
        if workgroup_is_extern(obj):
            messages.error(
                request,
                f'Working group "{name}" is required and cannot be deleted.',
            )
            return redirect(self.success_url)
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, f'Working group "{name}" was deleted.')
            return response
        except ProtectedError:
            messages.error(
                request,
                f'Working group "{name}" cannot be deleted because dependencies still exist '
                '(e.g. PI assignment or members).',
            )
            return redirect(self.success_url)

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete_selected':
            ids = [i for i in request.POST.getlist('selected_ids') if i]
            if not ids:
                messages.warning(request, "No entries selected.")
                return redirect(self.success_url)

            deleted, protected, system_blocked = _delete_workgroups_by_ids(ids)
            _workgroup_delete_messages(request, deleted, protected, system_blocked)
            return redirect(self.success_url)

        return super().post(request, *args, **kwargs)