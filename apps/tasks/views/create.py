"""
apps/tasks/views/create.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Task creation view with proper form handling and validation feedback
- Support for Purchase Orders with inline items and personnel recruitment funding formsets
- Sets creator_workgroup at save time (fixed workgroup for workflow coordinator routing)
- Clear error messages when form is invalid
- Correct redirect to /tasks/ after successful creation (redirect_to_my_tasks)

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView
from django.contrib import messages
from django.urls import reverse_lazy
from django.shortcuts import render, redirect

from django.utils import timezone

from ..models import Task, PurchaseOrderTask, PurchaseItem, StandardPurchaseItem, TaskComment
from ..forms import (
    PurchaseOrderTaskForm,
    PurchaseItemFormSet,
    GenericTextTaskForm,
    PersonnelReallocationTaskForm,
    PersonnelContractExtensionTaskForm,
    PersonnelRecruitmentTaskForm,
    RecruitmentFundingFormSet,
)
from ..recruitment_form_helpers import (
    build_recruitment_template_context,
    funding_formset_kwargs_from_post,
)
from ..recruitment_upload_cache import (
    clear_stashed_uploads,
    get_stashed_uploads,
    stash_recruitment_uploads,
)
from ..workflow_config import resolve_creator_workgroup
from .redirects import redirect_to_my_tasks
# GroupNames removed - using has_perm now


class TaskCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    template_name = 'tasks/task_create.html'
    success_url = reverse_lazy('tasks:my_tasks')

    def _get_task_type(self):
        return self.request.POST.get('task_type') or self.request.GET.get('type')

    def _is_quote_order_mode(self):
        if self._get_task_type() != 'purchase_order':
            return False
        variant = self.request.POST.get('po_variant') or self.request.GET.get('variant')
        return variant == 'quote'

    def _assign_personnel_task_number(self, instance):
        if instance.task_type not in (
            'personnel_reallocation', 'personnel_contract_extension', 'personnel_recruitment',
        ) or instance.task_number:
            return instance

        year = timezone.now().year
        if instance.task_type == 'personnel_reallocation':
            prefix = 'RA'
        elif instance.task_type == 'personnel_contract_extension':
            prefix = 'CE'
        else:
            prefix = 'REC'

        existing_numbers = Task.objects.filter(
            task_number__startswith=f'{prefix}-{year}-',
        ).values_list('task_number', flat=True)

        max_num = 0
        for num_str in existing_numbers:
            try:
                num = int(num_str.split('-')[-1])
                if num > max_num:
                    max_num = num
            except (IndexError, ValueError):
                continue

        new_task_number = f'{prefix}-{year}-{max_num + 1:04d}'
        instance.task_number = new_task_number
        instance.title = new_task_number
        instance.save(update_fields=['task_number', 'title'])
        return instance

    def _redirect_after_create(self, instance, *, message):
        self.object = instance
        messages.success(self.request, message)
        return redirect_to_my_tasks()

    def get_template_names(self):
        task_type = self._get_task_type()
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

        task_type = self._get_task_type()

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

        if task_type in ('personnel_reallocation', 'personnel_contract_extension', 'personnel_recruitment'):
            return user.has_perm('tasks.create_personnel_task')

        return False

    def get_form_class(self):
        task_type = self._get_task_type()
        mapping = {
            'purchase_order': PurchaseOrderTaskForm,
            'personnel_reallocation': PersonnelReallocationTaskForm,
            'personnel_contract_extension': PersonnelContractExtensionTaskForm,
            'personnel_recruitment': PersonnelRecruitmentTaskForm,
            'generic_text': GenericTextTaskForm,
        }
        return mapping.get(task_type, PurchaseOrderTaskForm)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        task_type = self._get_task_type()

        # Formulare die user + is_creation brauchen
        if task_type in (
            'purchase_order', 'generic_text', 'personnel_reallocation',
            'personnel_contract_extension', 'personnel_recruitment',
        ):
            kwargs['user'] = self.request.user
            kwargs['is_creation'] = True

        if task_type == 'purchase_order':
            kwargs['quote_order_mode'] = self._is_quote_order_mode()

        if task_type == 'personnel_recruitment':
            kwargs['stashed_uploads'] = get_stashed_uploads(self.request)

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
        task_type = self._get_task_type()
        context['task_type'] = task_type
        context['po_variant'] = (
            self.request.POST.get('po_variant')
            or self.request.GET.get('variant')
            or ''
        )

        if task_type == 'purchase_order' and not self._is_quote_order_mode():
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

        if task_type in ('personnel_recruitment', 'personnel_contract_extension'):
            context.update(build_recruitment_template_context())

        if task_type == 'personnel_recruitment':
            context['stashed_uploads'] = get_stashed_uploads(self.request)
            if self.request.method == 'POST':
                context['funding_formset'] = RecruitmentFundingFormSet(
                    self.request.POST,
                    **funding_formset_kwargs_from_post(self.request.POST, is_creation=True),
                )
            else:
                context['funding_formset'] = RecruitmentFundingFormSet(
                    is_creation=True,
                )
        return context

    def post(self, request, *args, **kwargs):
        if self._get_task_type() == 'personnel_recruitment':
            stash_recruitment_uploads(request)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        task_type = self._get_task_type()

        # Require confirmation checkbox for all task types
        if not self.request.POST.get('confirm_info'):
            messages.error(self.request, "Please confirm that all provided information is correct by checking the box.")
            return self.render_to_response(self.get_context_data(form=form))

        form.instance.creator = self.request.user.employee
        form.instance.creator_workgroup = resolve_creator_workgroup(self.request.user.employee)
        form.instance.task_type = task_type

        if task_type == 'purchase_order':
            if self._is_quote_order_mode():
                instance = form.save()
                return self._redirect_after_create(
                    instance,
                    message='Order with Quote created successfully.',
                )

            formset = self.get_context_data()['item_formset']
            if formset.is_valid():
                instance = form.save()
                formset.instance = instance
                formset.save()
                return self._redirect_after_create(
                    instance,
                    message='✅ Purchase Order created successfully.',
                )
            messages.error(self.request, "Please correct the errors in the items.")
            return self.render_to_response(self.get_context_data(form=form))

        if task_type == 'personnel_recruitment':
            funding_formset = RecruitmentFundingFormSet(
                self.request.POST,
                **funding_formset_kwargs_from_post(self.request.POST, is_creation=True),
            )
            if not funding_formset.is_valid():
                messages.error(self.request, "Please correct errors in the funding allocations.")
                return self.render_to_response(self.get_context_data(form=form))

            instance = form.save()
            funding_formset.instance = instance
            funding_formset.save()
            clear_stashed_uploads(self.request)
            instance = self._assign_personnel_task_number(instance)
            return self._redirect_after_create(
                instance,
                message=f'{instance.get_task_type_display()} created successfully.',
            )

        instance = form.save()
        instance = self._assign_personnel_task_number(instance)
        return self._redirect_after_create(
            instance,
            message=f'{instance.get_task_type_display()} created successfully.',
        )

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

