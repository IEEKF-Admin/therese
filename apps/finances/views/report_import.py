"""
UI for third-party funding report Excel import (preview → confirm → commit).
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.finances.models import CostCenter
from apps.finances.report_import.service import (
    analyze_uploaded_files,
    apply_import_plan,
    merge_user_decisions,
    refresh_personnel_checks,
)

SESSION_KEY = 'third_party_funding_import_plan'


@login_required
@permission_required('finances.import_third_party_funding_report', raise_exception=True)
@require_http_methods(['GET', 'POST'])
def third_party_funding_import(request):
    """Upload Excel file(s) and build a preview plan."""
    current_year = date.today().year

    if request.method == 'POST':
        files = request.FILES.getlist('report_files')
        year_raw = request.POST.get('import_year') or str(current_year)
        try:
            import_year = int(year_raw)
        except (TypeError, ValueError):
            messages.error(request, 'Import year must be a number.')
            return redirect('finances:third_party_funding_import')

        if not files:
            messages.error(request, 'Please select at least one Excel file.')
            return redirect('finances:third_party_funding_import')

        plan = analyze_uploaded_files(files, import_year=import_year)

        if plan.get('has_duplicate_files'):
            for meta in plan.get('upload_meta') or []:
                if not meta.get('is_duplicate'):
                    continue
                prior = meta.get('prior_import') or {}
                messages.error(
                    request,
                    (
                        f'Duplicate file blocked: "{meta.get("filename")}". '
                        f'Already imported on {str(prior.get("created_at", ""))[:19]} '
                        f'by {prior.get("uploaded_by", "unknown")} '
                        f'(SHA-256 {str(meta.get("file_sha256", ""))[:12]}…).'
                    ),
                )
            return redirect('finances:third_party_funding_import')

        if not plan['parents'] and plan.get('has_blocking_errors'):
            for f in plan.get('files') or []:
                for err in f.get('errors') or []:
                    messages.error(request, f"{f.get('filename')}: {err}")
            return redirect('finances:third_party_funding_import')

        if not plan['parents']:
            messages.error(request, 'No PSP parent data could be read from the uploaded file(s).')
            return redirect('finances:third_party_funding_import')

        request.session[SESSION_KEY] = plan
        request.session.modified = True
        return redirect('finances:third_party_funding_import_preview')

    return render(request, 'finances/report_import_upload.html', {
        'default_import_year': current_year,
    })


@login_required
@permission_required('finances.import_third_party_funding_report', raise_exception=True)
@require_http_methods(['GET', 'POST'])
def third_party_funding_import_preview(request):
    """Show analysis summary; on POST merge decisions and commit."""
    plan = request.session.get(SESSION_KEY)
    if not plan:
        messages.warning(request, 'No import plan in session. Please upload files again.')
        return redirect('finances:third_party_funding_import')

    # Re-check Personalkosten against current employees / funding allocations
    # (user may have created them in another tab).
    plan = refresh_personnel_checks(plan)
    request.session[SESSION_KEY] = plan
    request.session.modified = True

    cost_centers = CostCenter.objects.all().order_by('cost_center')

    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            request.session.pop(SESSION_KEY, None)
            messages.info(request, 'Import cancelled.')
            return redirect('finances:third_party_funding_import')

        if request.POST.get('action') == 'refresh_personnel':
            messages.info(
                request,
                'Personalkosten-Status neu geprüft (Mitarbeiter & Funding Allocations).',
            )
            return redirect('finances:third_party_funding_import_preview')

        plan, errors = merge_user_decisions(plan, request.POST)
        if errors:
            for err in errors:
                messages.error(request, err)
            request.session[SESSION_KEY] = plan
            request.session.modified = True
            return render(request, 'finances/report_import_preview.html', {
                'plan': plan,
                'cost_centers': cost_centers,
            })

        try:
            summary = apply_import_plan(plan, uploaded_by=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, 'finances/report_import_preview.html', {
                'plan': plan,
                'cost_centers': cost_centers,
            })

        request.session.pop(SESSION_KEY, None)
        messages.success(
            request,
            (
                f"Import finished: {summary['psp_created']} PSP created, "
                f"{summary['psp_updated']} PSP updated, "
                f"{summary['year_estimates_written']} year estimate(s), "
                f"{summary['true_spending_written']} true spending, "
                f"{summary['obligos_written']} obligo, "
                f"{summary['contacts_created']} contact(s), "
                f"{summary['cost_centers_created']} cost center(s), "
                f"{summary.get('import_logs', 0)} import log(s)."
            ),
        )
        for detail in summary.get('details') or []:
            messages.info(
                request,
                f"{detail['wbs_code']}: " + '; '.join(detail.get('actions') or []),
            )
        return redirect('finances:third_party_funding_import')

    return render(request, 'finances/report_import_preview.html', {
        'plan': plan,
        'cost_centers': cost_centers,
    })
