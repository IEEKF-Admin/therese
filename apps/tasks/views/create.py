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

from ..models import PurchaseOrderTask, PurchaseItem, StandardPurchaseItem, TaskComment
from ..forms import (
    PurchaseOrderTaskForm,
    PurchaseItemForm,
    GenericTextTaskForm,
    PersonnelReallocationTaskForm,
    PersonnelContractExtensionTaskForm,
)
# GroupNames removed - using has_perm now


PurchaseItemFormSet = inlineformset_factory(
    PurchaseOrderTask,
    PurchaseItem,
    form=PurchaseItemForm,
    extra=1,
    can_delete=True,
    fields=('product_name', 'product_description', 'link_to_product', 'order_number', 'unit_price', 'quantity')
)


class TaskCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    template_name = 'tasks/task_create.html'
    success_url = reverse_lazy('tasks:my_tasks')

    def get_template_names(self):
        task_type = self.request.GET.get('type')
        if task_type == 'generic_text':
            # Dedicated template only for General Requests
            return ['tasks/task_create_generic.html']
        # purchase_order + personnel_reallocation + personnel_contract_extension
        # all use the single existing task_create.html with conditional sections.
        return [self.template_name]

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False

        # All task creation requires a proper employee profile
        if not hasattr(user, 'employee') or user.employee is None:
            return False

        task_type = self.request.GET.get('type')

        if task_type == 'generic_text':
            return True

        if task_type == 'purchase_order':
            # Normal creation permission
            if user.has_perm('tasks.create_purchase_order') or user.has_perm('tasks.view_all_purchase_orders'):
                return True

            # Allow "Reorder" / copy if the user is allowed to view the original order
            copy_from_pk = self.request.GET.get('copy_from')
            if copy_from_pk:
                try:
                    from ..utils import can_view_purchase_order
                    original_task = PurchaseOrderTask.objects.get(pk=copy_from_pk)
                    return can_view_purchase_order(user, original_task)
                except PurchaseOrderTask.DoesNotExist:
                    return False

            return False

        if task_type in ('personnel_reallocation', 'personnel_contract_extension'):
            return user.has_perm('tasks.create_personnel_task')

        return False

    def get_form_class(self):
        task_type = self.request.GET.get('type')
        mapping = {
            'purchase_order': PurchaseOrderTaskForm,
            'personnel_reallocation': PersonnelReallocationTaskForm,
            'personnel_contract_extension': PersonnelContractExtensionTaskForm,
            'generic_text': GenericTextTaskForm,
        }
        return mapping.get(task_type, PurchaseOrderTaskForm)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        task_type = self.request.GET.get('type')

        # Formulare die user + is_creation brauchen
        if task_type in ('purchase_order', 'generic_text', 'personnel_reallocation', 'personnel_contract_extension'):
            kwargs['user'] = self.request.user
            kwargs['is_creation'] = True

        # Support copying from an existing Purchase Order
        copy_from_pk = self.request.GET.get('copy_from')
        if task_type == 'purchase_order' and copy_from_pk:
            try:
                original = PurchaseOrderTask.objects.get(pk=copy_from_pk)
                kwargs['initial'] = {
                    'supplier': original.supplier,
                    'wbs_element': original.wbs_element_id,
                    'priority': original.priority,
                    'assignee': original.assignee_id,
                }
            except PurchaseOrderTask.DoesNotExist:
                pass

        # Support pre-filling supplier from Standard Orders selection
        if task_type == 'purchase_order':
            standard_supplier = self.request.GET.get('supplier')
            if standard_supplier and 'initial' not in kwargs:
                kwargs['initial'] = {'supplier': standard_supplier}
            elif standard_supplier:
                kwargs['initial']['supplier'] = standard_supplier

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task_type = self.request.GET.get('type')
        context['task_type'] = task_type

        if task_type == 'purchase_order':
            copy_from_pk = self.request.GET.get('copy_from')
            standard_item_ids = self.request.GET.get('standard_items')

            if copy_from_pk and not self.request.POST:
                # Existing copy from PO logic
                try:
                    original = PurchaseOrderTask.objects.prefetch_related('items').get(pk=copy_from_pk)
                    initial_items = [
                        {
                            'product_name': item.product_name,
                            'product_description': item.product_description,
                            'link_to_product': item.link_to_product,
                            'unit_price': item.unit_price,
                            'quantity': item.quantity,
                            'order_number': getattr(item, 'order_number', ''),
                        }
                        for item in original.items.all()
                    ]
                    context['item_formset'] = PurchaseItemFormSet(initial=initial_items)
                    context['copy_from_task'] = original
                except PurchaseOrderTask.DoesNotExist:
                    context['item_formset'] = PurchaseItemFormSet()

            elif standard_item_ids and not self.request.POST:
                # New: Pre-fill from Standard Orders selection
                try:
                    ids = [int(x) for x in standard_item_ids.split(',') if x.strip().isdigit()]
                    standard_items = StandardPurchaseItem.objects.filter(id__in=ids)

                    initial_items = []
                    supplier = None

                    for std in standard_items:
                        if supplier is None:
                            supplier = std.supplier

                        initial_items.append({
                            'product_name': std.product_name,
                            'product_description': std.product_description,
                            'link_to_product': std.link_to_product,
                            'unit_price': std.unit_price,
                            'quantity': 1,
                            'order_number': std.order_number,
                        })

                    context['item_formset'] = PurchaseItemFormSet(initial=initial_items)

                    # Pre-fill supplier if we have one
                    if supplier:
                        context['initial_supplier'] = supplier

                except Exception:
                    context['item_formset'] = PurchaseItemFormSet()
            else:
                context['item_formset'] = PurchaseItemFormSet(
                    self.request.POST if self.request.method == 'POST' else None
                )
        return context

    def form_valid(self, form):
        task_type = self.request.GET.get('type')

        # Require confirmation checkbox for all task types
        if not self.request.POST.get('confirm_info'):
            messages.error(self.request, "Please confirm that all provided information is correct by checking the box.")
            return self.render_to_response(self.get_context_data(form=form))

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

        # Andere Task-Typen (spÃ¤ter)
        instance = form.save()

        # Automatische Task-Nummer fÃ¼r Personnel Reallocation und Contract Extension
        if instance.task_type in ['personnel_reallocation', 'personnel_contract_extension'] and not instance.task_number:
            from django.utils import timezone
            year = timezone.now().year

            if instance.task_type == 'personnel_reallocation':
                prefix = "RA"
            else:
                prefix = "CE"

            # NÃ¤chste laufende Nummer ermitteln
            existing_numbers = Task.objects.filter(
                task_number__startswith=f"{prefix}-{year}-"
            ).values_list('task_number', flat=True)

            max_num = 0
            for num_str in existing_numbers:
                try:
                    num = int(num_str.split('-')[-1])
                    if num > max_num:
                        max_num = num
                except (IndexError, ValueError):
                    continue

            new_task_number = f"{prefix}-{year}-{max_num + 1:04d}"
            instance.task_number = new_task_number
            instance.title = new_task_number  # FÃ¼r KompatibilitÃ¤t mit bestehender Anzeige
            instance.save(update_fields=['task_number', 'title'])

        messages.success(self.request, f"{instance.get_task_type_display()} created successfully.")
        return redirect('tasks:my_tasks')

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


def choose_task_type(request):
    """Auswahl des Task-Typs"""
    user = request.user
    user_groups = list(user.groups.values_list('name', flat=True)) if user.is_authenticated else []
    has_employee = user.is_authenticated and hasattr(user, 'employee') and user.employee is not None

    context = {
        'can_create_purchase': has_employee and (user.has_perm('tasks.create_purchase_order') or user.has_perm('tasks.view_all_purchase_orders')),
        'can_create_personnel': has_employee and user.has_perm('tasks.create_personnel_task'),
        'can_create_generic': has_employee,
    }
    return render(request, 'tasks/choose_task_type.html', context)

