from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.inventory.access import (
    filter_items_for_user,
    user_can_manage_inventory,
    user_can_view_all_inventory,
    user_can_view_inventory,
)
from apps.inventory.features import inventory_module_required
from apps.inventory.forms import InventoryItemForm
from apps.inventory.models import InventoryItem, InventoryItemType
from apps.inventory.services import allocate_item_code, apply_holder_change
from apps.hr.models import Employee


def _actor(request):
    return getattr(request.user, 'employee', None)


@login_required
@inventory_module_required
def item_list(request):
    if not user_can_view_inventory(request.user):
        messages.error(request, "You don't have permission to view inventory.")
        return redirect('tasks:my_tasks')

    qs = InventoryItem.objects.select_related('item_type', 'current_holder')
    qs = filter_items_for_user(qs, request.user)

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(description__icontains=q)
        )

    type_id = (request.GET.get('type') or '').strip()
    if type_id.isdigit():
        qs = qs.filter(item_type_id=int(type_id))

    status = (request.GET.get('status') or '').strip()
    if status == 'stock':
        qs = qs.filter(current_holder__isnull=True)
    elif status == 'issued':
        qs = qs.filter(current_holder__isnull=False)

    holder_id = (request.GET.get('holder') or '').strip()
    can_view_all = user_can_view_all_inventory(request.user)
    if can_view_all and holder_id.isdigit():
        qs = qs.filter(current_holder_id=int(holder_id))

    holders = Employee.objects.none()
    if can_view_all:
        holders = Employee.objects.visible().filter(
            inventory_items__isnull=False,
        ).distinct().order_by('last_name', 'first_name')

    return render(request, 'inventory/item_list.html', {
        'items': qs,
        'search_query': q,
        'type_filter': type_id,
        'status_filter': status,
        'holder_filter': holder_id,
        'item_types': InventoryItemType.objects.order_by('name'),
        'holders': holders,
        'can_manage': user_can_manage_inventory(request.user),
        'can_view_all': can_view_all,
    })


@login_required
@inventory_module_required
def item_create(request):
    if not user_can_manage_inventory(request.user):
        messages.error(request, "You don't have permission to create inventory items.")
        return redirect('inventory:item_list')

    if not InventoryItemType.objects.exists():
        messages.error(request, 'Define at least one item type under Global Settings first.')
        return redirect('inventory:item_list')

    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.code = allocate_item_code(item.item_type)
            new_holder = form.cleaned_data.get('current_holder')
            item.current_holder = None
            item.save()
            apply_holder_change(item, new_holder, actor=_actor(request))
            messages.success(request, f'Item {item.code} created.')
            return redirect('inventory:item_detail', pk=item.pk)
    else:
        form = InventoryItemForm()

    return render(request, 'inventory/item_form.html', {
        'form': form,
        'item': None,
        'can_edit': True,
        'issuances': [],
        'title': 'New inventory item',
    })


@login_required
@inventory_module_required
def item_detail(request, pk):
    if not user_can_view_inventory(request.user):
        messages.error(request, "You don't have permission to view inventory.")
        return redirect('tasks:my_tasks')

    item = get_object_or_404(
        InventoryItem.objects.select_related('item_type', 'current_holder'),
        pk=pk,
    )
    visible = filter_items_for_user(InventoryItem.objects.filter(pk=item.pk), request.user)
    if not visible.exists():
        messages.error(request, "You don't have permission to view this item.")
        return redirect('inventory:item_list')

    can_edit = user_can_manage_inventory(request.user)
    can_view_all = user_can_view_all_inventory(request.user)

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, "You don't have permission to edit inventory items.")
            return redirect('inventory:item_detail', pk=item.pk)
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.item_type = item.item_type
            saved.save()
            apply_holder_change(
                saved,
                form.cleaned_data.get('current_holder'),
                actor=_actor(request),
            )
            messages.success(request, f'Item {saved.code} saved.')
            return redirect('inventory:item_detail', pk=saved.pk)
    else:
        form = InventoryItemForm(instance=item)

    issuances = []
    if can_view_all or can_edit:
        issuances = item.issuances.select_related(
            'employee', 'issued_by', 'returned_by',
        )

    return render(request, 'inventory/item_form.html', {
        'form': form,
        'item': item,
        'can_edit': can_edit,
        'issuances': issuances,
        'title': f'{item.code} — {item.name}',
    })
