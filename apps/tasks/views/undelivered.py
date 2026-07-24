"""Undelivered purchase order lines — partial and full delivery."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.chemicals.access import user_can_mark_items_delivered
from apps.chemicals.services import apply_delivered_number, mark_purchase_items_delivered
from apps.tasks.models import PurchaseItem


@login_required
@require_http_methods(['GET', 'POST'])
def undelivered_purchase_items(request):
    """
    All undelivered purchase order lines (any product).

    Supports cumulative partial deliveries (delivered_number) and bulk full delivery.
    """
    if not user_can_mark_items_delivered(request.user):
        messages.error(request, "You don't have permission to manage deliveries.")
        return redirect('tasks:my_tasks')

    qs = (
        PurchaseItem.objects.filter(delivered=False)
        .select_related(
            'purchase_task',
            'purchase_task__creator',
        )
        .order_by('-purchase_task__created_at', 'pk')
    )

    if request.method == 'POST':
        action = request.POST.get('action') or ''

        if action == 'partial_delivery':
            item_id = request.POST.get('item_id')
            raw_number = request.POST.get('delivered_number')
            item = get_object_or_404(PurchaseItem, pk=item_id)
            try:
                apply_delivered_number(item, raw_number, user=request.user)
                item.refresh_from_db()
                if item.delivered:
                    messages.success(
                        request,
                        f'“{item.product_name}”: fully delivered '
                        f'({item.delivered_number}/{item.quantity}).',
                    )
                else:
                    messages.success(
                        request,
                        f'“{item.product_name}”: partial delivery recorded '
                        f'({item.delivered_number}/{item.quantity}).',
                    )
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect('orders:undelivered_items')

        if action == 'mark_delivered':
            ids = request.POST.getlist('selected_ids')
            items = list(PurchaseItem.objects.filter(pk__in=ids, delivered=False))
            count = mark_purchase_items_delivered(items, user=request.user)
            messages.success(request, f'{count} item(s) marked as fully delivered.')
            return redirect('orders:undelivered_items')

    return render(request, 'tasks/undelivered_items.html', {
        'items': qs[:2000],
    })
