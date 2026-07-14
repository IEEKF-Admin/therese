"""
apps/tasks/views/dashboard.py

My Tasks dashboard: non-PO tasks, purchase orders, personnel coordinator overview,
per-user archive, and optional login/document popups.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import Task, PurchaseOrderTask
from apps.hr.models import Employee
from ..utils import (
    get_purchase_orders_queryset,
    is_procurement_coordinator,
    is_procurement_approver,
    is_personnel_coordinator,
)


@login_required
def my_tasks(request):
    """Dashboard listing tasks and purchase orders visible to the current user."""

    # ----- Resolve employee profile -----
    try:
        employee = request.user.employee  # OneToOne from User to Employee
    except (AttributeError, Employee.DoesNotExist):
        employee = None

    if not employee:
        # Fallback for legacy test data without a proper OneToOne link.
        employee = Employee.objects.filter(user=request.user).first()

    if not employee:
        messages.warning(request, "No employee profile found for your account.")
        messages.info(
            request,
            "Please contact an administrator or create your employee profile in HR.",
        )
        return redirect('admin:index')

    user_groups = list(request.user.groups.values_list('name', flat=True))
    is_archive_view = request.GET.get('archive') == '1'

    # Archive / unarchive any task (PO or other) via POST.
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

    # Non-purchase-order tasks with per-user archive filtering.
    if is_archive_view:
        my_created = (
            Task.objects.filter(creator=employee, archived_by=employee)
            .exclude(task_type='purchase_order')
            .select_related('assignee', 'creator')
            .order_by('-created_at')
        )
        assigned_to_me = (
            Task.objects.filter(assignee=employee, archived_by=employee)
            .exclude(task_type='purchase_order')
            .select_related('assignee', 'creator')
            .order_by('-created_at')
        )
    else:
        my_created = (
            Task.objects.filter(creator=employee)
            .exclude(task_type='purchase_order')
            .exclude(archived_by=employee)
            .select_related('assignee', 'creator')
            .order_by('-created_at')
        )
        assigned_to_me = (
            Task.objects.filter(assignee=employee)
            .exclude(task_type='purchase_order')
            .exclude(archived_by=employee)
            .select_related('assignee', 'creator')
            .order_by('-created_at')
        )

    # Purchase orders — visibility from utils.get_purchase_orders_queryset().
    base_qs = get_purchase_orders_queryset(request.user)

    if is_archive_view:
        purchase_qs = base_qs.filter(archived_by=employee)
        page_title = "My Archive"
    else:
        purchase_qs = base_qs.exclude(archived_by=employee)
        page_title = "My Tasks"

    po_assigned_to_me = purchase_qs.filter(assignee=employee)
    po_created_by_me = purchase_qs.filter(creator=employee)

    is_coordinator = is_procurement_coordinator(request.user)
    is_approver = is_procurement_approver(request.user)

    # Coordinators see all visible POs; approvers see own + WBS-set from others.
    if is_coordinator:
        po_all_visible = purchase_qs
    elif is_approver:
        approver_extra = purchase_qs.filter(
            wbs_element__isnull=False,
        ).exclude(creator=employee)
        po_all_visible = (po_created_by_me | approver_extra).distinct()
    else:
        po_all_visible = None  # Requesters only see created/assigned split.

    personnel_all_visible = None
    if is_personnel_coordinator(request.user):
        personnel_qs = Task.objects.filter(
            task_type__in=[
                'personnel_reallocation',
                'personnel_contract_extension',
                'personnel_recruitment',
            ],
        ).select_related('assignee', 'creator').order_by('-created_at')
        if is_archive_view:
            personnel_all_visible = personnel_qs.filter(archived_by=employee)
        else:
            personnel_all_visible = personnel_qs.exclude(archived_by=employee)

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
        'is_personnel_coordinator': is_personnel_coordinator(request.user),
        'personnel_all_visible': personnel_all_visible,
        'is_archive_view': is_archive_view,
        'page_title': page_title,
    }

    import json
    from apps.accounts.login_popups import evaluate_login_popups, persist_popup_acknowledgements
    from apps.documents.popups import (
        evaluate_document_publish_popups,
        persist_document_publish_popup_acks,
    )

    employee = getattr(request.user, 'employee', None)
    popup_results = evaluate_login_popups(
        request.user,
        employee=employee,
        assigned_to_me=assigned_to_me,
        my_created=my_created,
    )
    doc_popup_results = evaluate_document_publish_popups(request.user)
    all_popup_results = popup_results + doc_popup_results

    if all_popup_results:
        persist_popup_acknowledgements(request.user, popup_results)
        persist_document_publish_popup_acks(request.user, doc_popup_results)
        popups = [
            {'text': p['text'], 'link': p.get('link', ''), 'url': p.get('url', '')}
            for p in all_popup_results
        ]
        context['login_popups'] = popups
        context['login_popups_json'] = json.dumps(popups)

    return render(request, 'tasks/my_tasks.html', context)