"""
apps/tasks/views/standard_orders.py

Standard Purchase Items (Catalog) management and selection flow.
All UI text in English.
Restricted to Procurement Coordinator + Procurement Approver.
"""
from django.shortcuts import render, redirect, get_object_or_404

from .redirects import redirect_to_my_tasks
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from apps.hr.models import Employee
# GroupNames import removed (old groups deleted)
from ..models import StandardPurchaseItem
from ..forms import StandardPurchaseItemForm
from ..utils import can_create_purchase_order


def _user_can_manage_standard_items(user) -> bool:
    """Only Procurement Coordinator and Procurement Approver may manage the catalog."""
    if not user or not user.is_authenticated:
        return False
    return (
        user.is_superuser or
        user.has_perm('tasks.manage_standard_order') or
        user.has_perm('tasks.view_all_purchase_orders')
    )


@login_required
def standard_orders_list(request):
    """List all Standard Purchase Items with search/filter (management view)."""
    if not _user_can_manage_standard_items(request.user):
        # Non-managers who can create POs are redirected to the selection/browsing view
        if can_create_purchase_order(request.user):
            return redirect('tasks:standard_order_select')
        messages.error(request, "You do not have permission to access Standard Orders.")
        return redirect('tasks:my_tasks')

    qs = StandardPurchaseItem.objects.select_related('created_by').all()

    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(supplier__icontains=search) |
            Q(product_name__icontains=search) |
            Q(order_number__icontains=search)
        )

    context = {
        'items': qs,
        'search_query': search,
    }
    return render(request, 'tasks/standard_orders/list.html', context)


@login_required
def standard_order_create(request):
    if not _user_can_manage_standard_items(request.user):
        messages.error(request, "Permission denied.")
        return redirect('tasks:standard_orders_list')

    if request.method == 'POST':
        form = StandardPurchaseItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            try:
                item.created_by = request.user.employee
            except (AttributeError, Employee.DoesNotExist):
                item.created_by = Employee.objects.first()  # fallback (should not happen)
            item.save()
            messages.success(request, "Standard item created successfully.")
            return redirect('tasks:standard_orders_list')
    else:
        form = StandardPurchaseItemForm()

    return render(request, 'tasks/standard_orders/form.html', {
        'form': form,
        'title': 'Create Standard Order Item',
        'is_edit': False,
    })


@login_required
def standard_order_edit(request, pk):
    if not _user_can_manage_standard_items(request.user):
        messages.error(request, "Permission denied.")
        return redirect('tasks:standard_orders_list')

    item = get_object_or_404(StandardPurchaseItem, pk=pk)

    if request.method == 'POST':
        form = StandardPurchaseItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "Standard item updated successfully.")
            return redirect('tasks:standard_orders_list')
    else:
        form = StandardPurchaseItemForm(instance=item)

    return render(request, 'tasks/standard_orders/form.html', {
        'form': form,
        'title': 'Edit Standard Order Item',
        'is_edit': True,
        'item': item,
    })


@login_required
def standard_order_delete(request, pk):
    if not _user_can_manage_standard_items(request.user):
        messages.error(request, "Permission denied.")
        return redirect('tasks:standard_orders_list')

    item = get_object_or_404(StandardPurchaseItem, pk=pk)

    if request.method == 'POST':
        item.delete()
        messages.success(request, "Standard item deleted.")
        return redirect('tasks:standard_orders_list')

    return render(request, 'tasks/standard_orders/confirm_delete.html', {'item': item})


@login_required
def standard_order_select(request):
    """
    Selection page for Standard Purchase Items when creating a new Purchase Order.

    Rules (per user spec):
    - Available to everyone who can create Purchase Orders.
    - User can select multiple items via checkboxes.
    - Once the first item is selected, only items from the same supplier remain selectable.
    - Other suppliers are grayed out and disabled.
    - "Order" button sends the selection to the normal PO create form (pre-filled).
    """
    if not can_create_purchase_order(request.user):
        messages.error(request, "You do not have permission to create Purchase Orders.")
        return redirect('tasks:my_tasks')

    # Get all standard items
    items = StandardPurchaseItem.objects.all().order_by('supplier', 'product_name')

    # Search support
    search = request.GET.get('q', '').strip()
    if search:
        items = items.filter(
            Q(supplier__icontains=search) |
            Q(product_name__icontains=search) |
            Q(product_description__icontains=search)
        )

    context = {
        'items': items,
        'search_query': search,
    }
    return render(request, 'tasks/standard_orders/select_for_po.html', context)


def standard_item_thumbnail(request, pk):
    """Serve the thumbnail (or original image) from the database."""
    item = get_object_or_404(StandardPurchaseItem, pk=pk)
    from django.http import HttpResponse

    if item.thumbnail:
        return HttpResponse(item.thumbnail, content_type='image/jpeg')
    elif item.image:
        return HttpResponse(item.image, content_type=item.image_content_type or 'image/jpeg')
    return HttpResponse(status=404)


@login_required
def save_standard_checkboxes(request, pk):
    """
    Special lightweight POST handler used by Approvers.
    They can only toggle "Mark as Standard" checkboxes on the detail page.
    Everything else remains read-only for them.
    """
    if not _user_can_manage_standard_items(request.user):
        messages.error(request, "Permission denied.")
        return redirect('tasks:my_tasks')

    from ..models import PurchaseOrderTask, PurchaseItem

    if request.method != 'POST':
        return redirect('tasks:task_detail', pk=pk)

    try:
        task = PurchaseOrderTask.objects.prefetch_related('items').get(pk=pk)
    except PurchaseOrderTask.DoesNotExist:
        messages.error(request, "Purchase Order not found.")
        return redirect('tasks:my_tasks')

    created = 0
    employee = getattr(request.user, 'employee', None)

    if employee is None:
        messages.error(request, "Your user account has no linked Employee profile. Cannot create Standard Orders.")
        return redirect('tasks:task_detail', pk=pk)

    for item in task.items.all():
        checkbox_name = f"standardize_item_{item.pk}"
        if checkbox_name in request.POST:
            if StandardPurchaseItem.already_exists(task.supplier, item.order_number):
                continue

            StandardPurchaseItem.objects.create(
                supplier=task.supplier,
                product_name=item.product_name,
                product_description=item.product_description,
                link_to_product=item.link_to_product,
                order_number=item.order_number,
                unit_price=item.unit_price,
                created_by=employee,
            )
            created += 1

    if created:
        messages.success(request, f"{created} item(s) added to Standard Orders.")
    else:
        messages.info(request, "No new standard items were added (duplicates or none selected).")

    return redirect_to_my_tasks()

