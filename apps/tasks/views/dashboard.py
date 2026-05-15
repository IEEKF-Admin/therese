"""
apps/tasks/views/dashboard.py
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import Task
from apps.hr.models import Employee
from ..utils import get_purchase_orders_queryset, is_procurement_coordinator


@login_required
def my_tasks(request):
    """Dashboard mit allen Tasks und Purchase Orders"""
    
    # ==================== EMPLOYEE PROFILE AUFLÖSEN ====================
    try:
        employee = request.user.employee  # OneToOne Relation
    except (AttributeError, Employee.DoesNotExist):
        employee = None

    if not employee:
        # Fallback: Versuche Employee über andere Wege zu finden (z.B. bei alten Testdaten)
        employee = Employee.objects.filter(user=request.user).first()

    if not employee:
        messages.warning(request, "No employee profile found for your account.")
        messages.info(request, "Please contact an administrator or create your employee profile in HR.")
        return redirect('admin:index')

    # Ab hier haben wir immer ein Employee-Objekt
    user_groups = list(request.user.groups.values_list('name', flat=True))
    is_archive_view = request.GET.get('archive') == '1'

    # Nicht-Purchase-Order Tasks
    my_created = Task.objects.filter(creator=employee).exclude(task_type='purchase_order')\
                   .select_related('assignee', 'creator').order_by('-created_at')

    assigned_to_me = Task.objects.filter(assignee=employee).exclude(task_type='purchase_order')\
                      .select_related('assignee', 'creator').order_by('-created_at')

    # Purchase Orders
    base_qs = get_purchase_orders_queryset(request.user)

    if is_archive_view:
        purchase_qs = base_qs.filter(status='completed')
        page_title = "Purchase Orders - Archive"
    else:
        purchase_qs = base_qs.exclude(status='completed')
        page_title = "Purchase Orders"

    my_purchase_orders = purchase_qs.filter(creator=employee)
    other_purchase_orders = purchase_qs.exclude(creator=employee)

    context = {
        'employee': employee,
        'user_groups': user_groups,
        'my_created': my_created,
        'assigned_to_me': assigned_to_me,
        'my_purchase_orders': my_purchase_orders,
        'other_purchase_orders': other_purchase_orders,
        'is_coordinator': is_procurement_coordinator(request.user),
        'is_archive_view': is_archive_view,
        'page_title': page_title,
    }
    return render(request, 'tasks/my_tasks.html', context)