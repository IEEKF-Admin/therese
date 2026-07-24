from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.chemicals.access import (
    filter_chemical_items_for_user,
    filter_chemicals_for_user,
    user_can_create_chemical,
    user_can_manage_chemical,
    user_can_manage_chemical_item,
    user_can_mark_items_delivered,
    user_can_view_chemical,
    user_can_view_chemical_item,
    user_can_view_chemical_item_list,
    user_can_view_chemical_list,
)
from apps.chemicals.forms import (
    ChemicalCASLookupForm,
    ChemicalForm,
    ChemicalItemForm,
    apply_lookup_meta_to_chemical,
    chemical_form_initial_from_pubchem,
)
from apps.chemicals.lookup import upsert_chemical_from_cas
from apps.chemicals.models import Chemical, ChemicalItem
from apps.chemicals.services import cas_live_check, mark_purchase_items_delivered
from apps.tasks.models import PurchaseItem


@login_required
@require_GET
def cas_check(request):
    """Live CAS / hazard check for purchase order forms."""
    raw = request.GET.get('cas') or request.GET.get('q') or ''
    return JsonResponse(cas_live_check(raw))


@login_required
def chemical_list(request):
    if not user_can_view_chemical_list(request.user):
        messages.error(request, "You don't have permission to view chemicals.")
        return redirect('tasks:my_tasks')

    qs = Chemical.objects.all().order_by('cas_number')
    qs = filter_chemicals_for_user(qs, request.user)
    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(cas_number__icontains=q)
            | Q(name__icontains=q)
            | Q(iupac_name__icontains=q)
        )

    can_manage_any = user_can_manage_chemical(request.user)
    rows = []
    for chem in qs[:500]:
        can_edit = user_can_manage_chemical(request.user, chem)
        rows.append({
            'chemical': chem,
            'can_edit': can_edit,
            'show_incomplete': can_edit and chem.is_incomplete,
        })

    return render(request, 'chemicals/chemical_list.html', {
        'rows': rows,
        'search_query': q,
        'can_manage_any': can_manage_any,
        'can_create': user_can_create_chemical(request.user),
    })


@login_required
def chemical_create(request):
    """
    Manually create a Chemical (CAS master):
    1) Enter CAS → Lookup (PubChem)
    2) Review/edit prefilled fields → Save
    """
    if not user_can_create_chemical(request.user):
        messages.error(request, "You don't have permission to create chemicals.")
        return redirect('chemicals:chemical_list')

    lookup_form = ChemicalCASLookupForm()
    form = None
    lookup_meta = None
    lookup_info = ''

    if request.method == 'POST':
        action = request.POST.get('action') or 'save'

        if action == 'lookup':
            lookup_form = ChemicalCASLookupForm(request.POST)
            if lookup_form.is_valid():
                cas = lookup_form.cleaned_data['cas_number']
                existing = Chemical.objects.filter(cas_number=cas).first()
                if existing:
                    if user_can_view_chemical(request.user, existing):
                        messages.info(
                            request,
                            f'Chemical with CAS {cas} already exists. Opened for review/edit.',
                        )
                        return redirect('chemicals:chemical_edit', pk=existing.pk)
                    messages.error(request, f'Chemical with CAS {cas} already exists.')
                    return redirect('chemicals:chemical_list')

                try:
                    initial, lookup_meta = chemical_form_initial_from_pubchem(cas)
                except Exception as exc:
                    initial = {'cas_number': cas}
                    lookup_meta = {'error': str(exc), 'found': False, 'pubchem_cid': None, 'raw': {}}
                form = ChemicalForm(initial=initial)
                if lookup_meta.get('found'):
                    lookup_info = (
                        'Data loaded from PubChem (free). Review the fields below, '
                        'adjust if needed, then save.'
                    )
                    if lookup_meta.get('error'):
                        lookup_info += f" Note: {lookup_meta['error']}"
                else:
                    lookup_info = (
                        'No PubChem match (or lookup failed). You can still fill in the '
                        'fields manually and save.'
                    )
                    if lookup_meta.get('error'):
                        lookup_info += f" ({lookup_meta['error']})"
                # Keep CAS in lookup form
                lookup_form = ChemicalCASLookupForm(initial={'cas_number': cas})

        else:
            # Save new chemical
            form = ChemicalForm(request.POST, request.FILES)
            # Re-show lookup box with same CAS
            cas_posted = (request.POST.get('cas_number') or '').strip()
            lookup_form = ChemicalCASLookupForm(initial={'cas_number': cas_posted})
            if form.is_valid():
                chemical = form.save()
                # Attach PubChem metadata from a fresh lookup snapshot if available
                # (fields already on form; store CID/raw if user came from lookup)
                try:
                    _, meta = chemical_form_initial_from_pubchem(chemical.cas_number)
                    apply_lookup_meta_to_chemical(chemical, meta)
                except Exception:
                    pass
                messages.success(request, f'Chemical {chemical.cas_number} created.')
                return redirect('chemicals:chemical_edit', pk=chemical.pk)
            lookup_info = 'Please correct the errors below.'
    else:
        lookup_form = ChemicalCASLookupForm()

    return render(request, 'chemicals/chemical_create.html', {
        'lookup_form': lookup_form,
        'form': form,
        'lookup_info': lookup_info,
        'lookup_meta': lookup_meta,
        'can_edit': True,
        'title': 'New Chemical (CAS)',
    })


@login_required
def chemical_edit(request, pk):
    chemical = get_object_or_404(Chemical, pk=pk)
    if not user_can_view_chemical(request.user, chemical):
        return HttpResponseForbidden('Access denied.')
    can_edit = user_can_manage_chemical(request.user, chemical)
    # Manual masters may not yet be linked to inventory items — allow edit
    # for anyone who may create chemicals (until inventory scoping applies).
    if not can_edit and user_can_create_chemical(request.user) and not chemical.items.exists():
        can_edit = True

    if request.method == 'POST':
        if not can_edit:
            return HttpResponseForbidden('Access denied.')
        action = request.POST.get('action') or 'save'
        if action == 'refresh_lookup':
            try:
                upsert_chemical_from_cas(chemical.cas_number, force_refresh=True)
                chemical.refresh_from_db()
                messages.success(request, 'Data refreshed from PubChem.')
            except Exception as exc:
                messages.error(request, f'Lookup failed: {exc}')
            return redirect('chemicals:chemical_edit', pk=chemical.pk)

        form = ChemicalForm(request.POST, request.FILES, instance=chemical, lock_cas=True)
        if form.is_valid():
            form.save()
            messages.success(request, 'Chemical saved.')
            return redirect('chemicals:chemical_list')
    else:
        form = ChemicalForm(instance=chemical, lock_cas=True)
        if not can_edit:
            for f in form.fields.values():
                f.disabled = True

    return render(request, 'chemicals/chemical_form.html', {
        'form': form,
        'chemical': chemical,
        'can_edit': can_edit,
        'title': f'Chemical {chemical.cas_number}',
        'show_refresh_lookup': can_edit,
    })


@login_required
def chemical_item_list(request):
    if not user_can_view_chemical_item_list(request.user):
        messages.error(request, "You don't have permission to view chemical items.")
        return redirect('tasks:my_tasks')

    qs = ChemicalItem.objects.select_related(
        'chemical', 'ordered_by', 'workgroup',
        'work_area', 'work_area__building',
        'storage_room', 'storage_room__building',
        'purchase_item',
    ).order_by('-created_at')
    qs = filter_chemical_items_for_user(qs, request.user)
    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(chemical__cas_number__icontains=q)
            | Q(product_name__icontains=q)
            | Q(work_area__room_number__icontains=q)
            | Q(work_area__colloquial_name__icontains=q)
            | Q(work_area__building__number__icontains=q)
            | Q(ordered_by__last_name__icontains=q)
            | Q(ordered_by__first_name__icontains=q)
        )
    status = (request.GET.get('status') or '').strip()
    if status in dict(ChemicalItem.Status.choices):
        qs = qs.filter(status=status)

    rows = []
    for item in qs[:500]:
        can_edit = user_can_manage_chemical_item(request.user, item)
        rows.append({
            'item': item,
            'can_edit': can_edit,
            'show_incomplete': can_edit and item.is_incomplete,
        })

    return render(request, 'chemicals/chemical_item_list.html', {
        'rows': rows,
        'search_query': q,
        'status_filter': status,
        'status_choices': ChemicalItem.Status.choices,
    })


@login_required
def chemical_item_edit(request, pk):
    item = get_object_or_404(
        ChemicalItem.objects.select_related(
            'chemical', 'ordered_by', 'workgroup',
            'purchase_item', 'purchase_item__purchase_task',
            'storage_room', 'storage_item',
        ),
        pk=pk,
    )
    if not user_can_view_chemical_item(request.user, item):
        return HttpResponseForbidden('Access denied.')
    can_edit = user_can_manage_chemical_item(request.user, item)
    if request.method == 'POST':
        if not can_edit:
            return HttpResponseForbidden('Access denied.')
        form = ChemicalItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Chemical item saved.')
            return redirect('chemicals:chemical_item_list')
    else:
        form = ChemicalItemForm(instance=item)
        if not can_edit:
            for f in form.fields.values():
                f.disabled = True

    return render(request, 'chemicals/chemical_item_form.html', {
        'form': form,
        'item': item,
        'can_edit': can_edit,
        'title': f'Chemical item {item.public_id.hex[:8]}',
    })


@login_required
def undelivered_purchase_items(request):
    """
    All undelivered purchase order lines (any product, not chemicals-only).

    Marking lines delivered also activates linked ChemicalItems when present and
    sets PO status to delivered once every line on that order is delivered.
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

    if request.method == 'POST' and request.POST.get('action') == 'mark_delivered':
        ids = request.POST.getlist('selected_ids')
        items = list(PurchaseItem.objects.filter(pk__in=ids, delivered=False))
        mark_purchase_items_delivered(items, user=request.user)
        messages.success(request, f'{len(items)} item(s) marked as delivered.')
        return redirect('chemicals:undelivered_items')

    # Live client-side filter; load a generous page of undelivered lines.
    return render(request, 'chemicals/undelivered_items.html', {
        'items': qs[:2000],
    })
