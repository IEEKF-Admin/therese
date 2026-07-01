#!/usr/bin/env python
"""
Promote Superuser to Staff Member

This script safely promotes a Django superuser (is_superuser=True) to a staff
member (is_staff=True). This is needed to access the Django admin interface
(/admin/) when a superuser was created without staff privileges.

It also sets password_changed=True so that the user is not forced through the
password change flow (which is usually not desired for administrators).

Usage:
    python promote_superuser_to_staff.py <username>

Examples:
    python promote_superuser_to_staff.py admin_demo
    python promote_superuser_to_staff.py myadmin

If no username is given, it will list all existing superusers.
"""

import os
import sys
import django

# Use the same settings as the production script
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'therese.settings.base')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()


def promote_to_staff(username):
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"❌ Error: User '{username}' does not exist.")
        return False

    print("\n" + "=" * 50)
    print(f"User: {user.username}")
    print(f"  Full name       : {user.get_full_name() or '-'}")
    print(f"  is_superuser    : {user.is_superuser}")
    print(f"  is_staff        : {user.is_staff}")
    print(f"  is_active       : {user.is_active}")

    if hasattr(user, 'password_changed'):
        print(f"  password_changed: {user.password_changed}")

    print("=" * 50)

    if user.is_staff:
        print("\n✅ User is already a staff member. Nothing to do.")
        return True

    if not user.is_superuser:
        print("\n⚠️  Warning: This user is NOT marked as superuser.")
        answer = input("Promote to staff anyway? [y/N]: ").strip().lower()
        if answer != 'y':
            print("Aborted.")
            return False

    # Perform the promotion
    user.is_staff = True

    # Also mark password as changed so admins don't get forced to the change page
    if hasattr(user, 'password_changed'):
        user.password_changed = True

    user.save()

    print("\n✅ Success!")
    print(f"   '{username}' is now a staff member.")
    print(f"   is_staff = {user.is_staff}")

    if hasattr(user, 'password_changed'):
        print(f"   password_changed = {user.password_changed}")

    print("\nYou can now log in with this user and access the admin area:")
    print("   https://<server-ip>:8000/admin/")
    print("=" * 50)
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCurrently existing superusers:\n")

        supers = User.objects.filter(is_superuser=True).order_by('username')
        if not supers.exists():
            print("  (no superusers found)")
        else:
            for u in supers:
                staff_marker = " + staff" if u.is_staff else ""
                print(f"  • {u.username}{staff_marker}")

        print("\nUsage: python promote_superuser_to_staff.py <username>")
        sys.exit(0)

    username = sys.argv[1]
    promote_to_staff(username)
