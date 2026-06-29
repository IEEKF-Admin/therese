"""
reset_test_data.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Löscht NUR die Testdaten, die durch create_test_data.py erstellt wurden
- Löscht nicht: Gebäude, Räume, Cost Centers, WBS Elements oder manuell angelegte Daten
- Sicher für wiederholtes Ausführen vor neuen Testdaten

Do not remove any existing requirements from this header without explicit instruction.
"""

import os
import django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings')
django.setup()

from apps.accounts.models import CustomUser
from apps.hr.models import Employee, Contract, FundingAllocation, SalarySupplement
from apps.tasks.models import PurchaseOrderTask, PurchaseItem


def reset_test_data():
    print("🗑️  Lösche nur Testdaten...\n")

    # Test-User anhand der bekannten Usernames löschen
    test_usernames = [
        'elenahar', 'markusber', 'sophiakle', 'tobiasneu', 'lenafisc',
        'julianrot', 'annasch', 'michaelwag', 'clarabec', 'paulric'
    ]
    
    users_deleted = CustomUser.objects.filter(username__in=test_usernames).delete()
    print(f"✓ Gelöscht: {users_deleted[0]} Test-Users")

    # Alle Employees löschen, die zu diesen Users gehören (sicher)
    employees = Employee.objects.filter(user__username__in=test_usernames)
    emp_count = employees.count()
    
    # Verknüpfte Daten löschen
    Contract.objects.filter(employee__in=employees).delete()
    FundingAllocation.objects.filter(employee__in=employees).delete()
    SalarySupplement.objects.filter(employee__in=employees).delete()
    
    employees.delete()
    print(f"✓ Gelöscht: {emp_count} Employees + zugehörige Contracts, Funding Allocations, Salary Supplements")

    # Purchase Orders löschen, die vom Skript erstellt wurden (anhand Titel-Muster)
    pos = PurchaseOrderTask.objects.filter(title__startswith="Bestellung ")
    po_count = pos.count()
    PurchaseItem.objects.filter(purchase_task__in=pos).delete()
    pos.delete()
    print(f"✓ Gelöscht: {po_count} Purchase Orders + Positionen")

    print("\n✅ Testdaten erfolgreich zurückgesetzt!")
    print("   (Echte Daten wie Gebäude, WBS-Elemente, Cost Centers bleiben erhalten)")


if __name__ == "__main__":
    reset_test_data()