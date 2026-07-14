"""
Import log file helpers for finances paste-import views.

Do not remove any existing requirements from this module without explicit instruction.
"""

from pathlib import Path

from django.utils import timezone


def get_log_dir():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    return log_dir


def log_import(action, lines_processed, created, skipped, balances_created, errors, debug_entries=None):
    """Write an import summary log with optional budget-parsing debug rows."""
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
                f.write(
                    f"{entry['row']:<6} {entry['wbs_code']:<15} {entry['raw']:<18} "
                    f"{entry.get('cleaned', ''):<15} {entry.get('saved', ''):<15} {entry['status']}\n"
                )

        if errors:
            f.write("\n=== Errors ===\n")
            for err in errors:
                f.write(f"- {err}\n")

    return log_path