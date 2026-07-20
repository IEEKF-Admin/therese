"""
Contact Person list (read-only) and manage (create / edit / delete) views.

English UI labels. Access is controlled by custom permissions:
- finances.view_contact_person_list
- finances.manage_contact_person
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from django.views.generic.edit import DeleteView

from ..forms import ContactPersonForm
from ..models import ContactPerson


class ContactPersonListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Read-only tabular list of all contact persons."""

    model = ContactPerson
    template_name = 'finances/contact_person_list.html'
    context_object_name = 'contact_persons'

    def get_queryset(self):
        qs = ContactPerson.objects.all().order_by('last_name', 'first_name')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(last_name__icontains=q)
                | Q(first_name__icontains=q)
                | Q(business_area__icontains=q)
                | Q(phone__icontains=q)
                | Q(email__icontains=q)
                | Q(comments__icontains=q)
            )
        return qs

    def test_func(self):
        user = self.request.user
        return (
            user.is_superuser
            or user.has_perm('finances.view_contact_person_list')
            or user.has_perm('finances.manage_contact_person')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Contact Persons'
        context['search_query'] = (self.request.GET.get('q') or '').strip()
        context['can_manage'] = (
            self.request.user.is_superuser
            or self.request.user.has_perm('finances.manage_contact_person')
        )
        return context


class ContactPersonManageListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Manage list with edit / delete actions and create entry point."""

    model = ContactPerson
    template_name = 'finances/contact_person_manage_list.html'
    context_object_name = 'contact_persons'

    def get_queryset(self):
        qs = ContactPerson.objects.all().order_by('last_name', 'first_name')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(last_name__icontains=q)
                | Q(first_name__icontains=q)
                | Q(business_area__icontains=q)
                | Q(phone__icontains=q)
                | Q(email__icontains=q)
                | Q(comments__icontains=q)
            )
        return qs

    def test_func(self):
        return (
            self.request.user.is_superuser
            or self.request.user.has_perm('finances.manage_contact_person')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Manage Contact Persons'
        context['search_query'] = (self.request.GET.get('q') or '').strip()
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete_selected':
            ids = [i for i in request.POST.getlist('selected_ids') if i]
            if not ids:
                messages.warning(request, 'No entries selected.')
                return redirect('finances:contact_person_manage')

            deleted = 0
            for pk in ids:
                try:
                    obj = ContactPerson.objects.get(pk=pk)
                    # FK on PSP / cost center is SET_NULL — safe to delete
                    obj.delete()
                    deleted += 1
                except ContactPerson.DoesNotExist:
                    pass
            if deleted:
                messages.success(request, f'{deleted} contact person(s) deleted.')
            return redirect('finances:contact_person_manage')
        return super().post(request, *args, **kwargs)


class ContactPersonCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = ContactPerson
    form_class = ContactPersonForm
    template_name = 'finances/contact_person_form.html'
    success_url = reverse_lazy('finances:contact_person_manage')

    def test_func(self):
        return (
            self.request.user.is_superuser
            or self.request.user.has_perm('finances.manage_contact_person')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Contact Person'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Contact person "{self.object}" was created.',
        )
        return response


class ContactPersonUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = ContactPerson
    form_class = ContactPersonForm
    template_name = 'finances/contact_person_form.html'
    success_url = reverse_lazy('finances:contact_person_manage')

    def test_func(self):
        return (
            self.request.user.is_superuser
            or self.request.user.has_perm('finances.manage_contact_person')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Contact Person — {self.object}'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Contact person "{self.object}" was updated.',
        )
        return response


class ContactPersonDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = ContactPerson
    template_name = 'finances/contact_person_confirm_delete.html'
    success_url = reverse_lazy('finances:contact_person_manage')

    def test_func(self):
        return (
            self.request.user.is_superuser
            or self.request.user.has_perm('finances.manage_contact_person')
        )

    def form_valid(self, form):
        name = str(self.get_object())
        response = super().form_valid(form)
        messages.success(self.request, f'Contact person "{name}" was deleted.')
        return response
