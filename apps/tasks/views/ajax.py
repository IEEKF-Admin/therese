"""AJAX endpoints for task forms."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.hr.models import Employee
from apps.tasks.extension_funding import serialize_open_funding


@login_required
@require_GET
def ajax_employee_current_funding(request):
    """Current open funding allocations for the selected employee."""
    user = request.user
    if not (
        user.is_superuser
        or user.has_perm('tasks.create_personnel_task')
        or user.has_perm('tasks.view_all_personnel_tasks')
        or user.has_perm('tasks.approve_personnel_task')
    ):
        return JsonResponse({'allocations': []})
    employee_id = request.GET.get('employee')
    if not employee_id:
        return JsonResponse({'allocations': []})
    employee = Employee.objects.filter(pk=employee_id).first()
    return JsonResponse({'allocations': serialize_open_funding(employee)})
