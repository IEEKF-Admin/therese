"""
create_test_data.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Creates demo users, employees, contracts, funding allocations, and sample purchase orders
- Assigns permission groups from apps.accounts.permissions.NEW_GROUPS
- Idempotent where possible (get_or_create for users and employees)
- Default password for all test users: test123

Do not remove any existing requirements from this header without explicit instruction.
"""

import os
import random
from datetime import date, timedelta
from decimal import Decimal

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings')
django.setup()

from django.contrib.auth.models import Group

from apps.accounts.models import CustomUser
from apps.accounts.permissions import NEW_GROUPS
from apps.finances.models import CostCenter, WBSElement
from apps.hr.models import Building, Contract, Employee, FundingAllocation, Room, SalarySupplement
from apps.tasks.models import PurchaseItem, PurchaseOrderTask

# Map demo role labels to permission group names (must exist in NEW_GROUPS).
ROLE_GROUP_MAPPING = {
    "PI": [
        "Employees - View", "Employees - Manage", "Purchase Orders - Create",
        "Personnel Tasks - Create", "PSP Elements - View", "Working Groups - Manage",
    ],
    "Procurement Requester": ["Purchase Orders - Create", "Standard Orders - View"],
    "Procurement Coordinator": [
        "Purchase Orders - Create", "Standard Orders - Manage",
        "Procurement - Coordination Rights", "Employees - View",
    ],
    "Procurement Approver": ["Procurement - Approval Rights", "Standard Orders - View"],
    "Personnel Approver": [
        "Personnel - Approval Rights", "Employees - View", "Employees - Manage",
    ],
    "Personnel Coordinator": [
        "Personnel - Coordination Rights", "Personnel Tasks - Create", "Employees - View",
    ],
    "Order Manager": ["Employees - View"],
}

USER_DATA = [
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


def create_test_data():
    print("Creating THERESE test data...\n")

    groups = {name: Group.objects.get_or_create(name=name)[0] for name in NEW_GROUPS}

    building, _ = Building.objects.get_or_create(
        number="A1", defaults={'name': 'Main Building'},
    )
    room, _ = Room.objects.get_or_create(
        building=building,
        room_number="3.12",
        defaults={'colloquial_name': 'Lab 312'},
    )
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

    employees = []
    for first, last, role in USER_DATA:
        username = f"{first.lower().replace(' ', '').replace('dr.', '')}{last.lower()[:3]}"

        user, created = CustomUser.objects.get_or_create(
            username=username,
            defaults={
                'first_name': first,
                'last_name': last,
                'email': f"{username}@example.com",
                'password_changed': True,
            },
        )
        if created:
            user.set_password("test123")
            user.save()

        for group_name in ROLE_GROUP_MAPPING.get(role, []):
            if group_name in groups:
                user.groups.add(groups[group_name])

        employee, emp_created = Employee.objects.get_or_create(
            employee_number=f"EMP{random.randint(10000, 99999)}",
            defaults={
                'first_name': first,
                'last_name': last,
                'user': user,
                'room': room,
                'email_professional': f"{username}@example.com",
                'cost_center': cc,
            },
        )
        if not emp_created and employee.user_id != user.pk:
            employee.user = user
            employee.save(update_fields=['user'])

        action = "created" if emp_created else "linked"
        print(f"  {action}: {first} {last} (user={username})")
        employees.append(employee)

    today = date.today()
    for emp in employees:
        for i in range(random.randint(2, 4)):
            start = today - timedelta(days=random.randint(100, 1200))
            end = start + timedelta(days=random.randint(300, 730))
            if i == 0:
                end = None if random.random() > 0.4 else end

            contract = Contract.objects.create(
                employee=emp,
                pay_scale_group=random.choice(['E 13', 'E 14', 'E 15', 'E 12']),
                experience_level=random.randint(1, 6),
                weekly_hours=random.choice([39.0, 38.5, 30.0]),
                valid_from=start,
                valid_until=end,
                is_active=(end is None or end >= today),
            )
            # Only one active contract per employee
            if contract.is_active:
                Contract.objects.filter(employee=emp, is_active=True).exclude(
                    pk=contract.pk
                ).update(is_active=False)

            for i in range(random.randint(1, 3)):
                fa_start = start
                fa_end = end
                FundingAllocation.objects.create(
                    contract=contract,
                    employee=emp,
                    wbs_element=random.choice(wbs_list),
                    workhours_percentage=round(random.uniform(20, 100), 2),
                    start_date=fa_start,
                    end_date=fa_end,
                    is_active=contract.is_active,
                )

    requesters = [
        emp for emp, (_, _, role) in zip(employees, USER_DATA)
        if role == "Procurement Requester"
    ]
    sample_orders = [
        ("Sigma-Aldrich", "Purchase Order Lab Chemicals"),
        ("Fisher Scientific", "Purchase Order Consumables"),
        ("VWR International", "Purchase Order Glassware"),
    ]
    for index, (supplier, title) in enumerate(sample_orders):
        creator = requesters[index % len(requesters)]
        po = PurchaseOrderTask.objects.create(
            creator=creator,
            task_type='purchase_order',
            title=title,
            supplier=supplier,
            wbs_element=random.choice(wbs_list),
            status='not_yet_processed',
        )
        PurchaseItem.objects.create(
            purchase_task=po,
            product_name=f"Test product {index + 1}",
            unit_price=Decimal('49.99'),
            quantity=random.randint(1, 5),
        )
    print(f"  created: {len(sample_orders)} sample purchase order(s)")

    print("\nTest data created successfully.")
    print("Password for all test users: test123")


if __name__ == "__main__":
    create_test_data()