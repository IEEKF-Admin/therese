"""
apps/hr/signals.py

Robust automatic creation of CustomUser for new Employees.
New employees' users are added to the baseline "Employee" group.
"""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

from .models import Employee
from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames

logger = logging.getLogger(__name__)


def ensure_employee_group_membership(user):
    """Add user to the baseline Employee group (idempotent)."""
    if user is None:
        return
    group, _ = Group.objects.get_or_create(name=GroupNames.EMPLOYEE)
    user.groups.add(group)


@receiver(post_save, sender=Employee)
def create_user_for_employee(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        with transaction.atomic():
            if not instance.user_id:
                first = (instance.first_name or "").strip().lower()
                last = (instance.last_name or "").strip().lower()

                base_username = (
                    f"{first}{last[0]}"
                    if first and last
                    else f"emp_{instance.employee_number or instance.pk}"
                )
                username = base_username
                counter = 1
                while CustomUser.objects.filter(username=username).exists():
                    username = (
                        f"{base_username}{last[:counter] if last else str(counter)}"
                    )
                    counter += 1
                    if counter > 15:
                        username = f"emp_{instance.pk}"
                        break

                user = CustomUser.objects.create_user(
                    username=username,
                    first_name=instance.first_name or "",
                    last_name=instance.last_name or "",
                    email=instance.email_professional or instance.email_private or "",
                    password="Welcome",
                )

                user.is_active = True
                user.is_staff = True
                user.password_changed = False
                user.save(update_fields=['is_active', 'is_staff', 'password_changed'])

                instance.user = user
                instance.save(update_fields=['user'])

                logger.info(f"Staff user created: {username} for {instance}")

            # Baseline role: every new employee gets the Employee group
            ensure_employee_group_membership(instance.user)

    except Exception as e:
        logger.error(f"Error creating user for {instance}: {e}", exc_info=True)
