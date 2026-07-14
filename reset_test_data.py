"""
reset_test_data.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Deletes ONLY test data created by create_test_data.py
- Does not delete: buildings, rooms, cost centers, WBS elements, or manually created data
- Safe to run repeatedly before regenerating test data

Do not remove any existing requirements from this header without explicit instruction.
"""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings')
django.setup()

from apps.accounts.models import CustomUser
from apps.hr.models import Contract, Employee, FundingAllocation, SalarySupplement
from apps.tasks.models import PurchaseItem, PurchaseOrderTask

TEST_USERNAMES = [
    'elenahar', 'markusber', 'sophiakle', 'tobiasneu', 'lenafisc',
    'julianrot', 'annasch', 'michaelwag', 'clarabec', 'paulric',
]


def reset_test_data():
    print("Deleting test data only...\n")

    users_deleted, _ = CustomUser.objects.filter(username__in=TEST_USERNAMES).delete()
    print(f"Deleted {users_deleted} test user(s) and related auth records")

    employees = Employee.objects.filter(user__username__in=TEST_USERNAMES)
    emp_count = employees.count()

    Contract.objects.filter(employee__in=employees).delete()
    FundingAllocation.objects.filter(employee__in=employees).delete()
    SalarySupplement.objects.filter(employee__in=employees).delete()
    employees.delete()
    print(
        f"Deleted {emp_count} employee(s) plus related contracts, "
        "funding allocations, and salary supplements"
    )

    pos = PurchaseOrderTask.objects.filter(title__startswith="Purchase Order ")
    po_count = pos.count()
    PurchaseItem.objects.filter(purchase_task__in=pos).delete()
    pos.delete()
    print(f"Deleted {po_count} purchase order(s) and line items")

    print("\nTest data reset complete.")
    print("(Buildings, WBS elements, and cost centers were not touched.)")


if __name__ == "__main__":
    reset_test_data()