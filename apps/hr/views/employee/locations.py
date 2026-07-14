"""
Location management views (buildings, rooms, phone numbers).

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView, UpdateView
from django.views.generic.edit import DeleteView

from ...forms import BuildingForm, PhoneNumberForm, RoomForm
from ...models import Building, PhoneNumber, Room


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

            for pk in request.POST.getlist('selected_buildings'):
                try:
                    Building.objects.get(pk=pk).delete()
                    deleted += 1
                except Exception:
                    errors += 1

            for pk in request.POST.getlist('selected_rooms'):
                try:
                    Room.objects.get(pk=pk).delete()
                    deleted += 1
                except Exception:
                    errors += 1

            for pk in request.POST.getlist('selected_phones'):
                try:
                    PhoneNumber.objects.get(pk=pk).delete()
                    deleted += 1
                except Exception:
                    errors += 1

            if deleted:
                messages.success(request, f"{deleted} entries deleted.")
            if errors:
                messages.error(request, f"{errors} entries could not be deleted (dependencies may exist).")

            return redirect('hr:location_management')

        return self.get(request, *args, **kwargs)


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
        context['item_type'] = 'Room'
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
            messages.error(
                request,
                f'Room "{display}" cannot be deleted (employees or phone numbers may still be assigned).',
            )
            return redirect(self.success_url)


class PhoneNumberDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = PhoneNumber
    template_name = 'hr/location_confirm_delete.html'
    success_url = reverse_lazy('hr:location_management')

    def test_func(self):
        return self.request.user.has_perm('hr.manage_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item_type'] = 'Phone Number'
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