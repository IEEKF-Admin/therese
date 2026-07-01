"""
apps/hr/signals.py

Robust automatic creation of CustomUser for new Employees.
"""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

from .models import Employee
from apps.accounts.models import CustomUser

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Employee)
def create_user_for_employee(sender, instance, created, **kwargs):
    if not created or instance.user_id:
        return

    try:
        with transaction.atomic():
            first = (instance.first_name or "").strip().lower()
            last = (instance.last_name or "").strip().lower()

            base_username = f"{first}{last[0]}" if first and last else f"emp_{instance.employee_number or instance.pk}"
            username = base_username
            counter = 1
            while CustomUser.objects.filter(username=username).exists():
                username = f"{base_username}{last[:counter] if last else str(counter)}"
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
            print(f"✅ Staff user created: {username} (Password: Welcome) for {instance}")

    except Exception as e:
        logger.error(f"Error creating user for {instance}: {e}", exc_info=True)

