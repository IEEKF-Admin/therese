"""
AJAX helpers for finances views.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from ..models import PayScale


@staff_member_required
@require_GET
def ajax_payscale_levels(request):
    """Return experience levels + salary for a selected pay scale group."""
    group = request.GET.get('group')
    if not group:
        return JsonResponse([], safe=False)

    scales = PayScale.objects.filter(pay_scale_group=group).order_by('experience_level')

    data = [{
        'level': scale.experience_level,
        'salary': str(scale.monthly_salary),
    } for scale in scales]

    return JsonResponse(data, safe=False)