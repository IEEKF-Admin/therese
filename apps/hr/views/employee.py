"""
apps/hr/views/employee.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
"""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView, UpdateView, ListView, TemplateView
from django.views.generic.edit import DeleteView
from django.db.models.deletion import ProtectedError
from django.db import models
from django.db.models import Q
from apps.accounts.permissions import user_can_assist
from django.urls import reverse_lazy

import json

from ..models import Employee, Workgroup, Building, Room, PhoneNumber
from ..forms import EmployeeForm, BuildingForm, RoomForm, PhoneNumberForm
from .employee_form_helpers import (
    ContractFormSet, FundingFormSet, 
    SalaryFormSet, WorkgroupFormSet
)
from apps.finances.models import PayScale


# = LIST VIEW =
@login_required
def employee_list(request):
    """Liste aller Mitarbeiter"""
    print("ðŸ” [DEBUG] employee_list view called")
    
    user_groups = list(request.user.groups.values_list('name', flat=True))
    print(f"ðŸ” User groups: {user_groups}")

    if not (request.user.is_superuser or 
            request.user.has_perm('hr.can_view_employees') or 
            request.user.has_perm('hr.manage_employee')):
        messages.error(request, "You don't have permission to view employees.")
        print("❌ Permission denied for employee list")
        return redirect('tasks:my_tasks')

    archive_mode = request.GET.get('archive') == '1'
    search_query = request.GET.get('q', '').strip()
    sort_field = request.GET.get('sort', 'last_name')
    sort_dir = request.GET.get('dir', 'asc')

    print(f"ðŸ” Archive mode: {archive_mode} | Search: '{search_query}'")

    employees = Employee.objects.select_related(
        'room__building', 'cost_center', 'user'
    ).prefetch_related('contracts')

    today = date.today()
    if archive_mode:
        employees = employees.filter(
            models.Q(contracts__valid_until__lt=today) | models.Q(contracts__isnull=True)
        ).distinct()
    else:
        employees = employees.filter(
            models.Q(contracts__valid_until__isnull=True) |
            models.Q(contracts__valid_until__gte=today)
        ).distinct()

    if search_query:
        employees = employees.filter(
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(employee_number__icontains=search_query)
        )

    # Sorting
    if sort_field == 'employee_number':
        order_by = 'employee_number'
    else:
        order_by = 'last_name' if sort_dir == 'asc' else '-last_name'
    if sort_dir == 'desc' and sort_field != 'employee_number':
        order_by = '-' + order_by

    employees = employees.order_by(order_by, 'first_name')

    context = {
        'employees': employees,
        'user_groups': user_groups,
        'archive_mode': archive_mode,
        'search_query': search_query,
        'current_sort': sort_field,
        'current_dir': sort_dir,
    }

    print(f"ðŸ” Returning {employees.count()} employees to template")

    # Bulk delete handling (for design consistency)
    if request.method == 'POST' and request.POST.get('action') == 'delete_selected':
        ids = request.POST.getlist('selected_ids')
        deleted = 0
        for eid in ids:
            try:
                Employee.objects.get(pk=eid).delete()
                deleted += 1
            except Exception:
                pass
        if deleted:
            messages.success(request, f"{deleted} employees deleted.")
        return redirect('hr:employee_list')

    return render(request, 'hr/employee_list.html', context)


# = CREATE VIEW =
class EmployeeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = '/hr/employees/'

    def test_func(self):
        print("ðŸ” [DEBUG] EmployeeCreateView.test_func called")
        user = self.request.user
        result = user.is_superuser or user.has_perm('hr.manage_employee')
        print(f"ðŸ” Permission check result: {result}")
        return result

    def get_context_data(self, **kwargs):
        print("ðŸ” [DEBUG] EmployeeCreateView.get_context_data called")
        context = super().get_context_data(**kwargs)
        context['contract_formset'] = ContractFormSet()
        context['funding_formset'] = FundingFormSet()
        context['salary_formset'] = SalaryFormSet()
        context['workgroup_formset'] = WorkgroupFormSet()

        # Current PayScales for JS cascading in Contracts inline
        current = PayScale.get_current()
        payscale_data = {}
        for ps in current:
            g = ps.pay_scale_group
            if g not in payscale_data:
                payscale_data[g] = []
            payscale_data[g].append({
                'experience_level': ps.experience_level,
                'monthly_salary': str(ps.monthly_salary),
            })
        context['current_payscales_json'] = json.dumps(payscale_data)
        return context

    def form_valid(self, form):
        print("ðŸ” [DEBUG] EmployeeCreateView.form_valid called")
        # ... (die gleiche form_valid Logik wie vorher)
        return super().form_valid(form)   # Platzhalter – bei Bedarf erweitern


# = UPDATE VIEW =
class EmployeeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = '/hr/employees/'

    def test_func(self):
        print("ðŸ” [DEBUG] EmployeeUpdateView.test_func called")
        user = self.request.user
        result = user.is_superuser or user.has_perm('hr.manage_employee')
        print(f"ðŸ” Permission check result: {result}")
        return result

    def get_context_data(self, **kwargs):
        print("ðŸ” [DEBUG] EmployeeUpdateView.get_context_data called - PK:", self.object.pk if self.object else None)
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['contract_formset'] = ContractFormSet(self.request.POST, instance=self.object)
            context['funding_formset'] = FundingFormSet(self.request.POST, instance=self.object)
            context['salary_formset'] = SalaryFormSet(self.request.POST, instance=self.object)
            context['workgroup_formset'] = WorkgroupFormSet(self.request.POST, instance=self.object)
        else:
            context['contract_formset'] = ContractFormSet(instance=self.object)
            context['funding_formset'] = FundingFormSet(instance=self.object)
            context['salary_formset'] = SalaryFormSet(instance=self.object)
            context['workgroup_formset'] = WorkgroupFormSet(instance=self.object)

        # Current PayScales for JS cascading in Contracts inline
        current = PayScale.get_current()
        payscale_data = {}
        for ps in current:
            g = ps.pay_scale_group
            if g not in payscale_data:
                payscale_data[g] = []
            payscale_data[g].append({
                'experience_level': ps.experience_level,
                'monthly_salary': str(ps.monthly_salary),
            })
        context['current_payscales_json'] = json.dumps(payscale_data)
        return context

    def form_valid(self, form):
        print("ðŸ” [DEBUG] EmployeeUpdateView.form_valid called - checking all inlines...")
        context = self.get_context_data()
        
        contract_valid = context['contract_formset'].is_valid()
        funding_valid = context['funding_formset'].is_valid()
        salary_valid = context['salary_formset'].is_valid()
        workgroup_valid = context['workgroup_formset'].is_valid()

        print(f"Contract valid: {contract_valid}")
        print(f"Funding valid: {funding_valid}")
        print(f"Salary valid: {salary_valid}")
        print(f"Workgroup valid: {workgroup_valid}")

        if not all([contract_valid, funding_valid, salary_valid, workgroup_valid]):
            if not contract_valid:
                messages.error(self.request, "❌ Fehler in den Verträgen (Contracts). Bitte prüfen Sie Pflichtfelder.")
            if not funding_valid:
                messages.error(self.request, "❌ Fehler in den Funding Allocations.")
            return self.form_invalid(form)

        self.object = form.save(commit=False)
        if not self.object.user_id and self.object.pk:
            existing = Employee.objects.filter(pk=self.object.pk).first()
            if existing and existing.user_id:
                self.object.user = existing.user

        self.object.save()

        for fs in [context['contract_formset'], context['funding_formset'],
                   context['salary_formset'], context['workgroup_formset']]:
            fs.instance = self.object
            fs.save()

        messages.success(self.request, "✅ Employee successfully saved!")
        return redirect(self.success_url)

    def form_invalid(self, form):
        print("❌ form_invalid called in UpdateView")
        messages.error(self.request, "Please correct the errors below.")
        return self.render_to_response(self.get_context_data(form=form))


class MyProfileView(LoginRequiredMixin, UpdateView):
    """Self-service view for employees to edit their own data (with restrictions)."""
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/my_profile.html'
    success_url = reverse_lazy('hr:my_profile')

    def get_object(self):
        user = self.request.user
        if not hasattr(user, 'employee') or user.employee is None:
            return None
        return user.employee

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object is None:
            messages.error(request, "No employee profile found for your account.")
            return redirect('tasks:my_tasks')
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field_name in ('monthly_salary', 'cost_center'):
            form.fields.pop(field_name, None)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp = self.object
        today = date.today()

        # Read-only current contracts
        context['current_contracts'] = emp.contracts.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=today)
        ).order_by('-valid_from')

        # Read-only current funding allocations
        context['current_fundings'] = emp.allocations.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).select_related('wbs_element').order_by('-start_date')

        # Workgroup formset for the inline/dropdown (to allow setting workgroup)
        if self.request.POST:
            workgroup_formset = WorkgroupFormSet(self.request.POST, instance=self.object)
        else:
            workgroup_formset = WorkgroupFormSet(instance=self.object)
        context['workgroup_formset'] = workgroup_formset

        context['is_self_profile'] = True
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        workgroup_formset = context.get('workgroup_formset')
        if workgroup_formset and workgroup_formset.is_valid():
            self.object = form.save()
            workgroup_formset.instance = self.object
            workgroup_formset.save()
            messages.success(self.request, "✅ Your profile has been updated!")
            return redirect(self.success_url)
        messages.error(self.request, "Please correct the errors below.")
        return self.form_invalid(form)


# = Assisting Admins dedicated views =

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

            deleted = 0
            protected = 0
            for pk in ids:
                try:
                    wg = Workgroup.objects.get(pk=pk)
                    wg.delete()
                    deleted += 1
                except Workgroup.DoesNotExist:
                    pass
                except ProtectedError:
                    protected += 1
            if deleted:
                messages.success(request, f"{deleted} working group(s) deleted.")
            if protected:
                messages.error(request, f"{protected} working group(s) could not be deleted (dependencies exist).")
            return redirect('hr:workgroup_list')
        return super().post(request, *args, **kwargs)


class WorkgroupCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Workgroup
    fields = ['short_name', 'long_name', 'pi', 'members']
    template_name = 'hr/workgroup_form.html'
    success_url = reverse_lazy('hr:workgroup_list')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')


class WorkgroupUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Workgroup
    fields = ['short_name', 'long_name', 'pi', 'members']
    template_name = 'hr/workgroup_form.html'
    success_url = reverse_lazy('hr:workgroup_list')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')


class LocationManagementView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'hr/location_management.html'

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['buildings'] = Building.objects.all().order_by('number')
        context['rooms'] = Room.objects.all().order_by('building__number', 'room_number')
        context['phones'] = PhoneNumber.objects.all().order_by('room__building__number', 'room__room_number')
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete_selected':
            deleted = 0
            errors = 0

            # Buildings
            for pk in request.POST.getlist('selected_buildings'):
                try:
                    Building.objects.get(pk=pk).delete()
                    deleted += 1
                except Exception:
                    errors += 1

            # Rooms
            for pk in request.POST.getlist('selected_rooms'):
                try:
                    Room.objects.get(pk=pk).delete()
                    deleted += 1
                except Exception:
                    errors += 1

            # Phones
            for pk in request.POST.getlist('selected_phones'):
                try:
                    PhoneNumber.objects.get(pk=pk).delete()
                    deleted += 1
                except Exception:
                    errors += 1

            if deleted:
                messages.success(request, f"{deleted} Einträge gelöscht.")
            if errors:
                messages.error(request, f"{errors} Einträge konnten nicht gelöscht werden (Abhängigkeiten?).")

            return redirect('hr:location_management')

        return self.get(request, *args, **kwargs)


# Dedicated CRUD for Buildings / Rooms / Phones (for Assisting Admins - non-admin views)

class BuildingCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Building
    form_class = BuildingForm
    template_name = 'hr/location_form.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'New Building'
        context['cancel_url'] = reverse_lazy('hr:location_management')
        return context


class BuildingUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Building
    form_class = BuildingForm
    template_name = 'hr/location_form.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Building'
        context['cancel_url'] = reverse_lazy('hr:location_management')
        return context


class RoomCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Room
    form_class = RoomForm
    template_name = 'hr/location_form.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'New Room'
        context['cancel_url'] = reverse_lazy('hr:location_management')
        return context


class RoomUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Room
    form_class = RoomForm
    template_name = 'hr/location_form.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Room'
        context['cancel_url'] = reverse_lazy('hr:location_management')
        return context


class PhoneNumberCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = PhoneNumber
    form_class = PhoneNumberForm
    template_name = 'hr/location_form.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'New Phone Number'
        context['cancel_url'] = reverse_lazy('hr:location_management')
        return context


class PhoneNumberUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = PhoneNumber
    form_class = PhoneNumberForm
    template_name = 'hr/location_form.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Phone Number'
        context['cancel_url'] = reverse_lazy('hr:location_management')
        return context


# = DELETE VIEWS for Assisting Admins =

class WorkgroupDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Workgroup
    template_name = 'hr/workgroup_confirm_delete.html'
    success_url = reverse_lazy('hr:workgroup_list')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_working_group')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        name = obj.short_name
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, f'Working group "{name}" was deleted.')
            return response
        except ProtectedError:
            messages.error(request, f'Working group "{name}" cannot be deleted because dependencies still exist (e.g. PI assignment or members).')
            return redirect(self.success_url)

    def post(self, request, *args, **kwargs):
        # Support bulk delete when coming from list checkboxes
        if request.POST.get('action') == 'delete_selected':
            ids = [i for i in request.POST.getlist('selected_ids') if i]
            if not ids:
                messages.warning(request, "No entries selected.")
                return redirect(self.success_url)

            deleted = 0
            protected = 0
            for pk in ids:
                try:
                    wg = Workgroup.objects.get(pk=pk)
                    wg.delete()
                    deleted += 1
                except Workgroup.DoesNotExist:
                    pass
                except ProtectedError:
                    protected += 1
            if deleted:
                messages.success(request, f"{deleted} working group(s) deleted.")
            if protected:
                messages.error(request, f"{protected} working group(s) could not be deleted (dependencies exist).")
            return redirect(self.success_url)

        # Normal single delete
        return super().post(request, *args, **kwargs)


class BuildingDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Building
    template_name = 'hr/location_confirm_delete.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item_type'] = 'Building'
        context['item_display'] = str(self.object)
        return context

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        display = str(obj)
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, f'Building "{display}" was deleted.')
            return response
        except ProtectedError:
            messages.error(request, f'Building "{display}" cannot be deleted because rooms still exist.')
            return redirect(self.success_url)


class RoomDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Room
    template_name = 'hr/location_confirm_delete.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item_type'] = 'Raum'
        context['item_display'] = str(self.object)
        context['building_info'] = str(self.object.building) if self.object.building else ''
        return context

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        display = f"{obj} ({obj.building})"
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, f'Room "{display}" was deleted.')
            return response
        except ProtectedError:
            messages.error(request, f'Room "{display}" cannot be deleted (employees or phone numbers may still be assigned).')
            return redirect(self.success_url)


class PhoneNumberDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = PhoneNumber
    template_name = 'hr/location_confirm_delete.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item_type'] = 'Telefonnummer'
        context['item_display'] = str(self.object)
        return context

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        display = str(obj)
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, f'Phone number "{display}" was deleted.')
            return response
        except ProtectedError:
            messages.error(request, f'Phone number "{display}" could not be deleted.')
            return redirect(self.success_url)

