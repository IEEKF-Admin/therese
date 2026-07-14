"""
PSP / WBS booking overview for authorized users.

Do not remove any existing requirements from this module without explicit instruction.
"""

import csv
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.hr.models import FundingAllocation
from apps.hr.workgroup_access import filter_by_user_workgroups, get_user_workgroups
from apps.tasks.models import PurchaseOrderTask
from ..models import PayScale, WBSElement


def calculate_funding_cost(allocation, period_start, period_end):
    """
    Calculate total salary cost for a FundingAllocation over the given period,
    respecting monthly structure, contracts and PayScale.
    """
    if not period_start:
        period_start = allocation.start_date
    if not period_end:
        period_end = allocation.end_date or date.today()

    overlap_start = max(allocation.start_date, period_start)
    alloc_end = allocation.end_date or date(9999, 12, 31)
    overlap_end = min(alloc_end, period_end)

    if overlap_start > overlap_end:
        return 0

    contract = allocation.employee.contracts.filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=overlap_start),
        valid_from__lte=overlap_start,
    ).order_by('-valid_from').first()

    if not contract or not contract.weekly_hours:
        return 0

    payscale = PayScale.objects.filter(
        pay_scale_group=contract.pay_scale_group,
        experience_level=contract.experience_level,
        effective_as_of__lte=overlap_start,
    ).order_by('-effective_as_of').first()

    if not payscale:
        return 0

    full_monthly = payscale.monthly_salary
    hours_ratio = Decimal(allocation.weekly_hours_allocated) / Decimal(contract.weekly_hours)
    prorated_monthly = full_monthly * hours_ratio

    months = (overlap_end.year - overlap_start.year) * 12 + (overlap_end.month - overlap_start.month) + 1

    return (prorated_monthly * months).quantize(Decimal("0.01"))


@login_required
def psp_elements(request):
    """PSP / WBS elements booking overview for authorized users."""
    user = request.user

    if not (user.is_superuser or
            user.has_perm('finances.view_psp_overview') or
            user.has_perm('finances.manage_psp_element')):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('tasks:my_tasks')

    user_workgroups = list(get_user_workgroups(user))

    wbs_id = request.GET.get('wbs', '')
    all_wbs = filter_by_user_workgroups(
        WBSElement.objects.all().order_by('wbs_code'),
        user,
    )

    current_year = date.today().year
    start_month = request.GET.get('start_month', '') or f'{current_year}-01'
    end_month = request.GET.get('end_month', '') or f'{current_year}-12'

    start_date = None
    end_date = None

    if start_month:
        try:
            y, m = map(int, start_month.split('-'))
            start_date = date(y, m, 1)
        except ValueError:
            pass

    if end_month:
        try:
            y, m = map(int, end_month.split('-'))
            last_day = (date(y, m, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            end_date = last_day
        except ValueError:
            pass

    filter_workgroup_id = request.GET.get('work_group', '')
    filter_workgroup = None
    if filter_workgroup_id and filter_workgroup_id != 'all':
        filter_workgroup = get_user_workgroups(user).filter(pk=filter_workgroup_id).first()

    wbs_qs = all_wbs
    if filter_workgroup:
        wbs_qs = wbs_qs.filter(work_group=filter_workgroup)

    if wbs_id and wbs_id != 'all':
        try:
            wbs_qs.get(id=wbs_id)
            wbs_qs = WBSElement.objects.filter(id=wbs_id)
        except WBSElement.DoesNotExist:
            wbs_id = 'all'

    pos_qs = PurchaseOrderTask.objects.filter(wbs_element__in=wbs_qs).select_related('wbs_element', 'creator')
    alloc_qs = FundingAllocation.objects.filter(wbs_element__in=wbs_qs).select_related('wbs_element', 'employee')

    if start_date:
        pos_qs = pos_qs.filter(created_at__date__gte=start_date)
        alloc_qs = alloc_qs.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=start_date),
            start_date__lte=(end_date or date(9999, 12, 31)),
        )

    if end_date:
        pos_qs = pos_qs.filter(created_at__date__lte=end_date)
        alloc_qs = alloc_qs.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=start_date or date.min),
            start_date__lte=end_date,
        )

    bookings = []

    for po in pos_qs:
        bookings.append({
            'type': 'Purchase Order',
            'wbs': po.wbs_element,
            'date': po.created_at.date() if po.created_at else None,
            'identifier': po.at_beleg_nummer or '-',
            'amount': getattr(po, 'total_price', 0),
            'person': str(po.creator) if po.creator else '-',
            'detail_url': reverse('tasks:task_detail', args=[po.pk]),
            'obj': po,
        })

    for alloc in alloc_qs:
        cost = calculate_funding_cost(alloc, start_date, end_date)

        bookings.append({
            'type': 'Funding Allocation',
            'wbs': alloc.wbs_element,
            'date': alloc.end_date,
            'identifier': str(alloc.employee),
            'amount': cost,
            'person': alloc.employee.get_full_name() if alloc.employee else '-',
            'end_date': alloc.end_date,
            'detail_url': reverse('hr:employee_list') + f'?q={alloc.employee.id}',
            'obj': alloc,
        })

    bookings.sort(key=lambda x: x['date'] or date.min, reverse=True)

    is_all = (not wbs_id or wbs_id == 'all')
    grouped_bookings = {}
    if is_all and bookings:
        grouped = defaultdict(list)
        for booking in bookings:
            grouped[booking['wbs']].append(booking)
        for wbs_obj, items in grouped.items():
            total = sum((item.get('amount') or 0) for item in items)
            grouped_bookings[wbs_obj] = {
                'items': items,
                'total': total,
            }

    if request.GET.get('export'):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="psp_bookings.csv"'
        writer = csv.writer(response)
        writer.writerow(['WBS', 'Date', 'Person', 'Amount'])
        for booking in bookings:
            writer.writerow([
                str(booking['wbs']),
                booking['date'],
                booking['person'],
                booking.get('amount', '-'),
            ])
        return response

    workgroup_choices = [('', '- All -')] + [(wg.id, str(wg)) for wg in user_workgroups]
    wbs_choices = [('', '- All -')] + [(w.id, str(w)) for w in all_wbs]

    context = {
        'wbs_choices': wbs_choices,
        'selected_wbs': wbs_id,
        'start_month': start_month,
        'end_month': end_month,
        'bookings': bookings,
        'grouped_bookings': grouped_bookings,
        'is_all': is_all,
        'workgroup_choices': workgroup_choices,
        'selected_workgroup': filter_workgroup_id,
        'title': 'PSP Elements',
    }

    return render(request, 'finances/psp_elements.html', context)