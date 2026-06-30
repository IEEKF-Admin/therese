"""
apps/tasks/views/dashboard.py
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import Task, PurchaseOrderTask
from apps.hr.models import Employee
from ..utils import get_purchase_orders_queryset, is_procurement_coordinator, is_procurement_approver


@login_required
def my_tasks(request):
    """Dashboard mit allen Tasks und Purchase Orders"""
    
    # ====== EMPLOYEE PROFILE AUFLÃ–SEN ======
    try:
        employee = request.user.employee  # OneToOne Relation
    except (AttributeError, Employee.DoesNotExist):
        employee = None

    if not employee:
        # Fallback: Versuche Employee Ã¼ber andere Wege zu finden (z.B. bei alten Testdaten)
        employee = Employee.objects.filter(user=request.user).first()

    if not employee:
        messages.warning(request, "No employee profile found for your account.")
        messages.info(request, "Please contact an administrator or create your employee profile in HR.")
        return redirect('admin:index')

    # Ab hier haben wir immer ein Employee-Objekt
    user_groups = list(request.user.groups.values_list('name', flat=True))
    is_archive_view = request.GET.get('archive') == '1'

    # Handle archiving / unarchiving for any task (PO or other)
    if request.method == 'POST':
        task_id = request.POST.get('archive_task') or request.POST.get('archive_po')
        if task_id:
            try:
                task = Task.objects.get(pk=task_id)
                if employee:
                    if request.POST.get('action') == 'unarchive':
                        task.archived_by.remove(employee)
                        messages.success(request, "Task removed from your archive.")
                    else:
                        task.archived_by.add(employee)
                        messages.success(request, "Task moved to your archive.")
                return redirect(f"{request.path}?archive=1" if is_archive_view else request.path)
            except Task.DoesNotExist:
                messages.error(request, "Task not found.")

    # Nicht-Purchase-Order Tasks - with archive filtering
    # Note: The .exclude(archived_by=...) will fail with "no such table" until you run migrations
    if is_archive_view:
        my_created = Task.objects.filter(creator=employee, archived_by=employee).exclude(task_type='purchase_order')\
                       .select_related('assignee', 'creator').order_by('-created_at')
        assigned_to_me = Task.objects.filter(assignee=employee, archived_by=employee).exclude(task_type='purchase_order')\
                          .select_related('assignee', 'creator').order_by('-created_at')
    else:
        my_created = Task.objects.filter(creator=employee).exclude(task_type='purchase_order').exclude(archived_by=employee)\
                       .select_related('assignee', 'creator').order_by('-created_at')
        assigned_to_me = Task.objects.filter(assignee=employee).exclude(task_type='purchase_order').exclude(archived_by=employee)\
                          .select_related('assignee', 'creator').order_by('-created_at')

    # Purchase Orders - now with same split as other tasks (Created by me vs Assigned to me)
    base_qs = get_purchase_orders_queryset(request.user)

    if is_archive_view:
        # In archive: show POs the user has personally archived (user-specific archive)
        purchase_qs = base_qs.filter(archived_by=employee)
        page_title = "My Archive"
    else:
        # Normal view: exclude those the user has archived themselves
        purchase_qs = base_qs.exclude(archived_by=employee)
        page_title = "My Tasks"

    # Split like normal tasks
    po_assigned_to_me = purchase_qs.filter(assignee=employee)
    po_created_by_me = purchase_qs.filter(creator=employee)

    is_coordinator = is_procurement_coordinator(request.user)
    is_approver    = is_procurement_approver(request.user)

    # For coordinators/approvers we may want to show additional visible POs
    # For simplicity, we add them to "Created by Me" section or have a separate logic.
    # For now, coordinators see all non-archived in a combined way if needed.
    if is_coordinator:
        # Coordinators see everything (except what they archived)
        po_all_visible = purchase_qs
    elif is_approver:
        # Approvers see their own + all with WBS set (as soon as coordinator sets WBS)
        approver_extra = purchase_qs.filter(
            wbs_element__isnull=False
        ).exclude(creator=employee)
        po_all_visible = (po_created_by_me | approver_extra).distinct()
    else:
        po_all_visible = None  # Requesters only see their own split

    context = {
        'employee': employee,
        'user_groups': user_groups,
        'my_created': my_created,
        'assigned_to_me': assigned_to_me,
        'po_assigned_to_me': po_assigned_to_me,
        'po_created_by_me': po_created_by_me,
        'po_all_visible': po_all_visible,
        'is_coordinator': is_coordinator,
        'is_approver': is_approver,
        'is_archive_view': is_archive_view,
        'page_title': page_title,
    }
    return render(request, 'tasks/my_tasks.html', context)

