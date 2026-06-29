"""
apps/finances/views.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Import view for Cost Centers
- Import view for WBS Elements with detailed debug logging
- Ignores the last sum line of each table
- Supports pasting multiple tables at once
- Detailed budget parsing with debug output in log and console
- All user-facing text must be in English

Do not remove any existing requirements from this header without explicit instruction.
"""

import csv
import datetime
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import CostCenter, WBSElement, WBSElementInitialBalance


def get_log_dir():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    return log_dir


def log_import(action, lines_processed, created, skipped, balances_created, errors, debug_entries=None):
    """Enhanced logging with detailed budget parsing information"""
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"import_{action}_{timestamp}.txt"
    log_path = get_log_dir() / filename

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"THERESE Import Log - {action.replace('_', ' ').title()}\n")
        f.write(f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Lines processed: {lines_processed}\n")
        f.write(f"Created WBS Elements: {created}\n")
        f.write(f"Updated WBS Elements: {skipped}\n")
        f.write(f"Initial Balances created/updated: {balances_created}\n")
        f.write(f"Errors: {len(errors)}\n\n")

        if debug_entries:
            f.write("=== Detailed Budget Parsing Debug ===\n")
            f.write(f"{'Row':<6} {'WBS Code':<15} {'Raw Budget':<18} {'Cleaned':<15} {'Saved Value':<15} Status\n")
            f.write("-" * 85 + "\n")
            for entry in debug_entries:
                f.write(f"{entry['row']:<6} {entry['wbs_code']:<15} {entry['raw']:<18} "
                        f"{entry.get('cleaned',''):<15} {entry.get('saved',''):<15} {entry['status']}\n")

        if errors:
            f.write("\n=== Errors ===\n")
            for err in errors:
                f.write(f"- {err}\n")

    return log_path


@staff_member_required
def import_cost_centers(request):
    """Import Cost Centers from pasted Excel table"""
    if request.method == 'POST':
        pasted_data = request.POST.get('pasted_data', '').strip()
        if not pasted_data:
            messages.error(request, "No data pasted.")
            return redirect('import_cost_centers')

        lines = pasted_data.splitlines()
        reader = csv.reader(lines, delimiter='\t')
        
        created = 0
        skipped = 0
        errors = []
        processed = 0

        next(reader, None)  # Skip header

        for row in reader:
            processed += 1
            if len(row) < 2:
                continue
            cost_center_code = row[1].strip() if len(row) > 1 else ""
            if '/' not in cost_center_code:
                continue

            try:
                if not CostCenter.objects.filter(cost_center=cost_center_code).exists():
                    CostCenter.objects.create(cost_center=cost_center_code)
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"Row {processed}: {str(e)}")

        log_path = log_import("cost_centers", processed, created, skipped, 0, errors)
        messages.success(request, f"Cost Centers import completed: {created} created, {skipped} skipped.")
        messages.info(request, f"Log file: {log_path.name}")
        return redirect('admin:finances_costcenter_changelist')

    return render(request, 'finances/import_cost_centers.html')


@staff_member_required
def import_wbs_elements(request):
    """Import WBS Elements + Initial Balance for current year - robust column detection"""
    if request.method == 'POST':
        pasted_data = request.POST.get('pasted_data', '').strip()
        if not pasted_data:
            messages.error(request, "No data pasted.")
            return redirect('import_wbs_elements')

        lines = pasted_data.splitlines()
        reader = csv.reader(lines, delimiter='\t')
        
        created_wbs = 0
        updated_wbs = 0
        balances_created = 0
        errors = []
        debug_entries = []
        processed = 0
        current_year = datetime.date.today().year
        in_table = False
        budget_col_index = 2   # default fallback

        for row_num, row in enumerate(reader, 1):
            processed += 1
            if not row or len(row) < 3:
                in_table = False
                continue

            # Detect table header and find the correct column indices
            row_str = [str(cell).strip().lower() for cell in row]
            if "projekt" in row_str[0] and "psp bezeichnung" in row_str[1]:
                in_table = True
                # Find the column with "freigegebenes budget"
                for i, cell in enumerate(row_str):
                    if "freigegeben" in cell or "budget" in cell:
                        budget_col_index = i
                        print(f"DEBUG: Found budget column at index {i}")
                        break
                continue

            if not in_table:
                continue

            # Extract fields using dynamic indices
            wbs_code = str(row[0]).strip() if len(row) > 0 else ""
            title = str(row[1]).strip() if len(row) > 1 else ""
            budget_str = str(row[budget_col_index]).strip() if len(row) > budget_col_index else ""

            # Skip sum line
            if not wbs_code or len(wbs_code) < 3 or wbs_code.startswith(" "):
                continue

            try:
                wbs, created = WBSElement.objects.get_or_create(
                    wbs_code=wbs_code,
                    defaults={'title': title}
                )
                if created:
                    created_wbs += 1
                else:
                    updated_wbs += 1

                raw_budget = budget_str
                cleaned = ""
                saved_value = 0.00
                status = "Skipped (no budget)"

                if budget_str and budget_str.strip() not in ["0,00", "0.00", "0", ""]:
                    try:
                        cleaned = budget_str.replace('.', '').replace(',', '.').strip()
                        initial_balance = float(cleaned)
                        saved_value = initial_balance

                        WBSElementInitialBalance.objects.update_or_create(
                            wbs_element=wbs,
                            year=current_year,
                            defaults={'initial_balance': initial_balance}
                        )
                        balances_created += 1
                        status = "Saved"

                        print(f"DEBUG SUCCESS: {wbs_code:15} | Raw: '{raw_budget}' → Cleaned: {cleaned} → Saved: {initial_balance:.2f} €")

                    except ValueError as ve:
                        status = "Parse Error"
                        errors.append(f"Row {row_num}: Cannot convert '{budget_str}' for {wbs_code} → {ve}")
                        print(f"DEBUG FAILED:  {wbs_code:15} | Raw: '{raw_budget}' → Error: {ve}")
                else:
                    WBSElementInitialBalance.objects.update_or_create(
                        wbs_element=wbs,
                        year=current_year,
                        defaults={'initial_balance': 0.00}
                    )
                    balances_created += 1
                    status = "Saved as 0.00"

                debug_entries.append({
                    'row': row_num,
                    'wbs_code': wbs_code,
                    'raw': raw_budget,
                    'cleaned': cleaned,
                    'saved': f"{saved_value:.2f}",
                    'status': status
                })

            except Exception as e:
                errors.append(f"Row {row_num} ({wbs_code}): {str(e)}")

        log_path = log_import("wbs_elements", processed, created_wbs, updated_wbs, balances_created, errors, debug_entries)

        messages.success(
            request, 
            f"Import successful: {created_wbs} new + {updated_wbs} updated WBS Elements | "
            f"{balances_created} Initial Balances for year {current_year}."
        )
        if errors:
            messages.warning(request, f"{len(errors)} errors – check the detailed log.")

        messages.info(request, f"Detailed log file created: {log_path.name}")
        return redirect('admin:finances_wbselement_changelist')

    return render(request, 'finances/import_wbs_elements.html')
    
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.admin.views.decorators import staff_member_required
from .models import PayScale


@staff_member_required
@require_GET
def ajax_payscale_levels(request):
    """Return experience levels for a given pay scale group"""
    group = request.GET.get('group')
    if not group:
        return JsonResponse([], safe=False)

    scales = PayScale.objects.filter(pay_scale_group=group).order_by('experience_level')
    data = [{
        'level': scale.experience_level,
        'salary': str(scale.monthly_salary)
    } for scale in scales]

    return JsonResponse(data, safe=False)
    
# === AJAX für PayScale Dropdowns ===
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.admin.views.decorators import staff_member_required
from .models import PayScale


@staff_member_required
@require_GET
def ajax_payscale_levels(request):
    """Return experience levels + salary for a selected pay scale group"""
    group = request.GET.get('group')
    if not group:
        return JsonResponse([], safe=False)

    scales = PayScale.objects.filter(pay_scale_group=group).order_by('experience_level')
    
    data = [{
        'level': scale.experience_level,
        'salary': str(scale.monthly_salary)
    } for scale in scales]

    return JsonResponse(data, safe=False)