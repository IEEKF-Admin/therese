"""AJAX endpoints for task forms."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.hr.models import Employee
from apps.hr.validity import contract_validity_defaults
from apps.tasks.extension_funding import serialize_open_funding


def _empty_funding_payload():
    return {
        'allocations': [],
        'has_contract': False,
        'is_permanent': False,
        'valid_until': '',
        'max_until': '',
    }


@login_required
@require_GET
def ajax_employee_current_funding(request):
    """Current open funding allocations and contract validity for the selected employee."""
    user = request.user
    if not (
        user.is_superuser
        or user.has_perm('tasks.create_personnel_task')
        or user.has_perm('tasks.view_all_personnel_tasks')
        or user.has_perm('tasks.approve_personnel_task')
    ):
        return JsonResponse(_empty_funding_payload())
    employee_id = request.GET.get('employee')
    if not employee_id:
        return JsonResponse(_empty_funding_payload())
    employee = Employee.objects.filter(pk=employee_id).first()
    defaults = contract_validity_defaults(employee)
    return JsonResponse({
        'allocations': serialize_open_funding(employee),
        'has_contract': defaults['has_contract'],
        'is_permanent': defaults['is_permanent'],
        'valid_until': defaults['valid_until_de'],
        'max_until': defaults['max_until_de'],
    })
