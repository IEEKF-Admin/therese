"""
Paste-import views for cost centers, WBS elements, and pay scales.

Do not remove any existing requirements from this module without explicit instruction.
"""

import csv
import datetime
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from ..models import CostCenter, PayScale, WBSElement, WBSElementYearEstimate
from .import_logging import log_import


@staff_member_required
def import_cost_centers(request):
    """Import Cost Centers from pasted Excel table."""
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
    """Import WBS Elements + Initial Balance for current year - robust column detection."""
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
        budget_col_index = 2

        for row_num, row in enumerate(reader, 1):
            processed += 1
            if not row or len(row) < 3:
                in_table = False
                continue

            row_str = [str(cell).strip().lower() for cell in row]
            if "projekt" in row_str[0] and "psp bezeichnung" in row_str[1]:
                in_table = True
                for i, cell in enumerate(row_str):
                    if "freigegeben" in cell or "budget" in cell:
                        budget_col_index = i
                        print(f"DEBUG: Found budget column at index {i}")
                        break
                continue

            if not in_table:
                continue

            wbs_code = str(row[0]).strip() if len(row) > 0 else ""
            title = str(row[1]).strip() if len(row) > 1 else ""
            budget_str = str(row[budget_col_index]).strip() if len(row) > budget_col_index else ""

            if not wbs_code or len(wbs_code) < 3 or wbs_code.startswith(" "):
                continue

            try:
                wbs, created = WBSElement.objects.get_or_create(
                    wbs_code=wbs_code,
                    defaults={'title': title},
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

                        WBSElementYearEstimate.objects.update_or_create(
                            wbs_element=wbs,
                            year=current_year,
                            defaults={'funding': initial_balance},
                        )
                        balances_created += 1
                        status = "Saved"

                        print(
                            f"DEBUG SUCCESS: {wbs_code:15} | Raw: '{raw_budget}' -> "
                            f"Cleaned: {cleaned} -> Saved: {initial_balance:.2f} EUR"
                        )

                    except ValueError as ve:
                        status = "Parse Error"
                        errors.append(f"Row {row_num}: Cannot convert '{budget_str}' for {wbs_code} -> {ve}")
                        print(f"DEBUG FAILED:  {wbs_code:15} | Raw: '{raw_budget}' -> Error: {ve}")
                else:
                    WBSElementYearEstimate.objects.update_or_create(
                        wbs_element=wbs,
                        year=current_year,
                        defaults={'funding': 0.00},
                    )
                    balances_created += 1
                    status = "Saved as 0.00"

                debug_entries.append({
                    'row': row_num,
                    'wbs_code': wbs_code,
                    'raw': raw_budget,
                    'cleaned': cleaned,
                    'saved': f"{saved_value:.2f}",
                    'status': status,
                })

            except Exception as e:
                errors.append(f"Row {row_num} ({wbs_code}): {str(e)}")

        log_path = log_import(
            "wbs_elements", processed, created_wbs, updated_wbs, balances_created, errors, debug_entries,
        )

        messages.success(
            request,
            f"Import successful: {created_wbs} new + {updated_wbs} updated WBS Elements | "
            f"{balances_created} year estimate(s) for year {current_year}.",
        )
        if errors:
            messages.warning(request, f"{len(errors)} errors – check the detailed log.")

        messages.info(request, f"Detailed log file created: {log_path.name}")
        return redirect('admin:finances_wbselement_changelist')

    return render(request, 'finances/import_wbs_elements.html')


def parse_pay_scales_table(pasted_data, effective_date):
    """Parse pasted table and create/update PayScale entries."""
    created = 0
    updated = 0
    errors = []

    lines = pasted_data.strip().splitlines()
    if not lines:
        return 0, 0, ["No data provided."]

    reader = csv.reader(lines, delimiter='\t')
    try:
        header = next(reader)
    except StopIteration:
        return 0, 0, ["Empty table."]

    level_strs = [x.strip() for x in header[1:] if x.strip()]
    try:
        levels = [int(level) for level in level_strs]
    except ValueError:
        return 0, 0, ["Invalid experience level header row."]

    for row in reader:
        if not row or not row[0].strip():
            continue
        group = row[0].strip()

        for idx, level in enumerate(levels):
            col_idx = idx + 1
            if col_idx >= len(row):
                break
            val_str = row[col_idx].strip()
            if not val_str:
                continue

            try:
                val_str = val_str.replace(',', '.').replace(' ', '').replace('EUR', '').strip()
                salary = Decimal(val_str)

                _, was_created = PayScale.objects.update_or_create(
                    pay_scale_group=group,
                    experience_level=level,
                    effective_as_of=effective_date,
                    defaults={'monthly_salary': salary},
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except (InvalidOperation, ValueError, Exception) as e:
                errors.append(f"{group} level {level}: {str(e)}")

    return created, updated, errors


@login_required
def import_pay_scales(request):
    """Import Pay Scale / TV-L data from pasted table for Personnel Coordinators."""
    if not (request.user.is_superuser or request.user.has_perm('finances.import_pay_scale')):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('tasks:my_tasks')

    if request.method == 'POST':
        effective_str = request.POST.get('effective_as_of', '').strip()
        pasted_data = request.POST.get('pasted_data', '').strip()

        if not effective_str or not pasted_data:
            messages.error(request, "Please provide an effective date and paste the table.")
            return redirect('finances:import_pay_scales')

        try:
            effective_date = date.fromisoformat(effective_str)
        except ValueError:
            messages.error(request, "Invalid date format. Use YYYY-MM-DD.")
            return redirect('finances:import_pay_scales')

        created, updated, errors = parse_pay_scales_table(pasted_data, effective_date)

        if errors:
            for err in errors[:5]:
                messages.warning(request, f"Error: {err}")
            if len(errors) > 5:
                messages.warning(request, f"... and {len(errors) - 5} more errors.")

        if created or updated:
            messages.success(
                request,
                f"Import successful: {created} created, {updated} updated for effective date {effective_date}.",
            )
        else:
            messages.info(request, "No new or updated entries were created.")

        return redirect('finances:import_pay_scales')

    today = date.today().isoformat()
    return render(request, 'finances/import_pay_scales.html', {
        'default_date': today,
    })