"""
create_test_data.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
"""

import os
import django
from datetime import date, timedelta
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings')
django.setup()

from django.contrib.auth.models import Group
from apps.accounts.models import CustomUser
from apps.hr.models import Employee, Building, Room, Contract, FundingAllocation, SalarySupplement
from apps.finances.models import CostCenter, WBSElement
from apps.tasks.models import PurchaseOrderTask, PurchaseItem


def create_test_data():
    print("🚀 Erstelle umfangreiche Testdaten für THERESE...\n")

    from apps.accounts.permissions import NEW_GROUPS, OLD_GROUPS

    # Groups - only new permission groups
    groups = {name: Group.objects.get_or_create(name=name)[0] for name in NEW_GROUPS}
    perm_groups = {name: Group.objects.get_or_create(name=name)[0] for name in NEW_PERMISSION_GROUPS}

    # Basic structures
    building, _ = Building.objects.get_or_create(number="A1", defaults={'name': 'Main Building'})
    room, _ = Room.objects.get_or_create(building=building, room_number="3.12",
                                         defaults={'colloquial_name': 'Lab 312'})
    cc, _ = CostCenter.objects.get_or_create(cost_center="4711/2026")

    wbs_list = []
    for code, title in [
        ("D-025.0353.1", "AI Research & Development"),
        ("D-025.0353.2", "Infrastructure & Laboratories"),
        ("D-025.0353.3", "Staff & Training"),
        ("D-025.0354.1", "Medical Technology Project"),
    ]:
        wbs, _ = WBSElement.objects.get_or_create(wbs_code=code, defaults={'title': title})
        wbs_list.append(wbs)

    # ====== USERS + EMPLOYEES ======
    user_data = [
        ("Dr. Elena", "Hartmann", "PI"),
        ("Markus", "Berger", "Procurement Requester"),
        ("Dr. Sophia", "Klein", "PI"),
        ("Tobias", "Neumann", "Procurement Coordinator"),
        ("Lena", "Fischer", "Procurement Requester"),
        ("Dr. Julian", "Roth", "Order Manager"),
        ("Anna", "Schreiber", "Personnel Approver"),
        ("Michael", "Wagner", "Procurement Requester"),
        ("Dr. Clara", "Becker", "PI"),
        ("Paul", "Richter", "Procurement Coordinator"),
    ]

    employees = []
    for first, last, role in user_data:
        username = f"{first.lower().replace(' ', '').replace('dr.', '')}{last.lower()[:3]}"

        # User erstellen
        user, created = CustomUser.objects.get_or_create(
            username=username,
            defaults={
                'first_name': first,
                'last_name': last,
                'email': f"{username}@example.com",
                'password_changed': True,
            }
        )
        if created:
            user.set_password("test123")
            user.save()

        user.groups.add(groups[role])

        # Assign new permission-based groups (using role names from test data for convenience)
        new_group_mapping = {
            "PI": ["Employees - View", "Employees - Manage", "Purchase Orders - Create", "Personnel Tasks - Create", "PSP Elements - View", "Working Groups - Manage"],
            "Procurement Requester": ["Purchase Orders - Create", "Standard Orders - View"],
            "Procurement Coordinator": ["Purchase Orders - Create", "Standard Orders - Manage", "Procurement - Coordination Rights", "Employees - View"],
            "Procurement Approver": ["Procurement - Approval Rights", "Standard Orders - View"],
            "Personnel Approver": ["Personnel - Approval Rights", "Employees - View", "Employees - Manage"],
            "Personnel Coordinator": ["Personnel - Coordination Rights", "Personnel Tasks - Create", "Employees - View"],
            "Order Manager": ["Employees - View"],
        }
        for gname in new_group_mapping.get(role, []):
            if gname in perm_groups:
                perm_groups[gname].user_set.add(user)

        # Employee explizit mit User verknüpfen
        employee, created = Employee.objects.get_or_create(
            employee_number=f"EMP{random.randint(10000,99999)}",
            defaults={
                'first_name': first,
                'last_name': last,
                'user': user,                    # WICHTIG: Verknüpfung
                'room': room,
                'email_professional': f"{username}@example.com",
                'cost_center': cc,
            }
        )
        if created:
            print(f"✓ Neu erstellt: {first} {last} → Employee + User")
        else:
            employee.user = user
            employee.save()
            print(f"✓ Verknüpft: {first} {last} (Employee existierte bereits)")

        employees.append(employee)

    # ====== CONTRACTS & FUNDING ALLOCATIONS ======
    today = date.today()

    for emp in employees:
        # Contracts (2–4 pro Person, inkl. abgelaufener)
        for i in range(random.randint(2, 4)):
            start = today - timedelta(days=random.randint(100, 1200))
            end = start + timedelta(days=random.randint(300, 730))
            if i == 0:  # Aktueller Vertrag
                end = None if random.random() > 0.4 else end

            Contract.objects.create(
                employee=emp,
                pay_scale_group=random.choice(['E 13', 'E 14', 'E 15', 'E 12']),
                experience_level=random.randint(1, 6),
                weekly_hours=random.choice([39.0, 38.5, 30.0]),
                valid_from=start,
                valid_until=end,
            )

        # Funding Allocations
        for i in range(random.randint(2, 5)):
            start = today - timedelta(days=random.randint(30, 800))
            end = start + timedelta(days=random.randint(120, 600))
            if i == 0:
                end = None if random.random() > 0.5 else end

            FundingAllocation.objects.create(
                employee=emp,
                wbs_element=random.choice(wbs_list),
                weekly_hours_allocated=round(random.uniform(12, 39), 2),
                start_date=start,
                end_date=end,
            )

    print("\nðŸŽ‰ Testdaten erfolgreich erstellt!")
    print("Passwort für alle: test123")


if __name__ == "__main__":
    create_test_data()

