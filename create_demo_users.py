"""
create_demo_users.py
Erstellt Demo-Benutzer fÃ¼r THERESE-PrÃ¤sentationen.
Diese Benutzer mÃ¼ssen beim Login NICHT ihr Passwort Ã¤ndern.

Verwendung:
    cd C:\Django\Therese
    venv\Scripts\python.exe create_demo_users.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.hr.models import Employee

User = get_user_model()

# = DEMO ACCOUNTS =
DEMO_USERS = [
    {
        "username": "demo1",
        "password": "demo123",
        "first_name": "Anna",
        "last_name": "MÃ¼ller",
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

>>>>>>> 6d6462209f0ab46def16f2edf4a2bef3e493f84e
    },
]

def create_demo_users():
    print("=== THERESE Demo-Benutzer erstellen ===\n")

    created = 0
    existing = 0

    for data in DEMO_USERS:
        user, was_created = User.objects.get_or_create(
            username=data["username"],
            defaults={
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data["email"],
                "password_changed": True,   # â† WICHTIG: Kein Passwort-Ã„nderungs-Zwang
                "is_staff": data.get("is_staff", False),

                "is_superuser": data.get("is_superuser", False),

>>>>>>> 6d6462209f0ab46def16f2edf4a2bef3e493f84e
            }
        )

        if was_created:
            user.set_password(data["password"])
            user.save()
            created += 1
            print(f"[NEU]     : {data['username']:12} | Passwort: {data['password']:10} | {data['first_name']} {data['last_name']}")
        else:
            # Update existing user to be demo-ready
            user.password_changed = True
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.email = data["email"]
            if data.get("is_staff"):
                user.is_staff = True

            if data.get("is_superuser"):
                user.is_superuser = True

>>>>>>> 6d6462209f0ab46def16f2edf4a2bef3e493f84e
            user.set_password(data["password"])
            user.save()
            existing += 1
            print(f"[UPDATE]  : {data['username']:12} | Passwort: {data['password']:10} | {data['first_name']} {data['last_name']}")

    print(f"\n=== Fertig ===")
    print(f"Neu erstellt:   {created}")
    print(f"Aktualisiert:   {existing}")
    print(f"Gesamt Demo-Accounts: {len(DEMO_USERS)}")
    print("\nAlle Benutzer kÃ¶nnen sich jetzt mit Passwort 'demo123' (bzw. 'admin123') einloggen,")
    print("ohne dass sie beim ersten Login ihr Passwort Ã¤ndern mÃ¼ssen.\n")


if __name__ == "__main__":
    create_demo_users()


