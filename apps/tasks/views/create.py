"""
apps/tasks/views/create.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Task creation view with proper form handling and validation feedback
- Support for Purchase Orders with inline items
- Clear error messages when form is invalid
- Correct redirect after successful creation

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView
from django.contrib import messages
from django.urls import reverse_lazy
from django.shortcuts import render, redirect
from django.forms.models import inlineformset_factory

from ..models import PurchaseOrderTask, PurchaseItem
from ..forms import (
    PurchaseOrderTaskForm,
    PurchaseItemForm,
)


PurchaseItemFormSet = inlineformset_factory(
    PurchaseOrderTask,
    PurchaseItem,
    form=PurchaseItemForm,
    extra=1,
    can_delete=True,
    fields=('product_name', 'product_description', 'link_to_product', 'unit_price', 'quantity')
)


class TaskCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    template_name = 'tasks/task_create.html'
    success_url = reverse_lazy('tasks:my_tasks')

    def test_func(self):
        return self.request.user.groups.filter(name__in=['Procurement Requester', 'PI']).exists()

    def get_form_class(self):
        task_type = self.request.GET.get('type')
        mapping = {
            'purchase_order': PurchaseOrderTaskForm,
            'personnel_reallocation': None,   # später implementieren
            'personnel_contract_extension': None,
            'generic_text': None,
        }
        return mapping.get(task_type, PurchaseOrderTaskForm)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['is_creation'] = True
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task_type = self.request.GET.get('type')
        context['task_type'] = task_type

        if task_type == 'purchase_order':
            context['item_formset'] = PurchaseItemFormSet(
                self.request.POST if self.request.method == 'POST' else None
            )
        return context

    def form_valid(self, form):
        task_type = self.request.GET.get('type')
        form.instance.creator = self.request.user.employee
        form.instance.task_type = task_type

        if task_type == 'purchase_order':
            formset = self.get_context_data()['item_formset']
            if formset.is_valid():
                instance = form.save()
                formset.instance = instance
                formset.save()
                messages.success(self.request, "✅ Purchase Order created successfully.")
                return redirect('tasks:my_tasks')
            else:
                messages.error(self.request, "Please correct the errors in the items.")
                return self.render_to_response(self.get_context_data(form=form))

        # Andere Task-Typen (später)
        instance = form.save()
        messages.success(self.request, f"{instance.get_task_type_display()} created successfully.")
        return redirect('tasks:my_tasks')

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


def choose_task_type(request):
    """Auswahl des Task-Typs"""
    user_groups = list(request.user.groups.values_list('name', flat=True))
    context = {
        'can_create_purchase': 'Procurement Requester' in user_groups or 'PI' in user_groups,
        'can_create_personnel': 'PI' in user_groups,
    }
    return render(request, 'tasks/choose_task_type.html', context)