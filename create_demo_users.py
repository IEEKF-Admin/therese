"""
create_demo_users.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Creates demo users for THERESE presentations
- Sets password_changed=True so users are not forced to change password on first login
- Idempotent: updates existing demo accounts to the expected state

Usage:
    cd C:\\Django\\therese
    venv\\Scripts\\python.exe create_demo_users.py

Do not remove any existing requirements from this header without explicit instruction.
"""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

DEMO_USERS = [
    {
        "username": "demo1",
        "password": "demo123",
        "first_name": "Anna",
        "last_name": "Muller",
        "email": "anna.mueller@example.com",
    },
    {
        "username": "demo2",
        "password": "demo123",
        "first_name": "Thomas",
        "last_name": "Weber",
        "email": "thomas.weber@example.com",
    },
    {
        "username": "demo3",
        "password": "demo123",
        "first_name": "Lisa",
        "last_name": "Schmidt",
        "email": "lisa.schmidt@example.com",
    },
    {
        "username": "demo4",
        "password": "demo123",
        "first_name": "Michael",
        "last_name": "Klein",
        "email": "michael.klein@example.com",
    },
    {
        "username": "admin_demo",
        "password": "admin123",
        "first_name": "Admin",
        "last_name": "Demo",
        "email": "admin.demo@example.com",
        "is_staff": True,
        "is_superuser": True,
    },
]


def create_demo_users():
    print("=== THERESE demo users ===\n")

    created = 0
    updated = 0

    for data in DEMO_USERS:
        user, was_created = User.objects.get_or_create(
            username=data["username"],
            defaults={
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data["email"],
                "password_changed": True,
                "is_staff": data.get("is_staff", False),
                "is_superuser": data.get("is_superuser", False),
            },
        )

        if was_created:
            user.set_password(data["password"])
            user.save()
            created += 1
            print(f"[NEW]     {data['username']:12} password={data['password']:10} {data['first_name']} {data['last_name']}")
        else:
            user.password_changed = True
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.email = data["email"]
            if data.get("is_staff"):
                user.is_staff = True
            if data.get("is_superuser"):
                user.is_superuser = True
            user.set_password(data["password"])
            user.save()
            updated += 1
            print(f"[UPDATE]  {data['username']:12} password={data['password']:10} {data['first_name']} {data['last_name']}")

    print(f"\nDone: {created} created, {updated} updated ({len(DEMO_USERS)} demo accounts total).")
    print("Users can log in without being forced to change their password on first login.\n")


if __name__ == "__main__":
    create_demo_users()