"""
apps/hr/views/ajax.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- AJAX endpoints for cascading dropdowns (Building → Room → Phone)
- Accessible to all authorized HR roles (PI, Personnel Approver, etc.)
- No dependency on non-existent utils
- Comprehensive English logging

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.http import JsonResponse
# GroupNames import removed - using permissions instead of old groups
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

from ..models import Room, PhoneNumber


@login_required
@require_GET
def ajax_rooms_by_building(request):
    """Return all rooms for a given building"""
    if not (request.user.is_superuser or 
            request.user.has_perm('hr.can_view_employees') or 
            request.user.has_perm('hr.manage_employee')):
        return JsonResponse([], safe=False)

    building_id = request.GET.get('building')
    if not building_id:
        return JsonResponse([], safe=False)

    rooms = Room.objects.filter(building_id=building_id).order_by('room_number')
    data = [{'id': room.id, 'display': str(room)} for room in rooms]
    return JsonResponse(data, safe=False)


@login_required
@require_GET
def ajax_phonenumbers_by_room(request):
    """Return all phone numbers for a given room"""
    if not (request.user.is_superuser or 
            request.user.has_perm('hr.can_view_employees') or 
            request.user.has_perm('hr.manage_employee')):
        return JsonResponse([], safe=False)

    room_id = request.GET.get('room')
    if not room_id:
        return JsonResponse([], safe=False)

    phones = PhoneNumber.objects.filter(room_id=room_id).order_by('phone_number')
    data = [{'id': phone.id, 'phone_number': phone.phone_number} for phone in phones]
    return JsonResponse(data, safe=False)

