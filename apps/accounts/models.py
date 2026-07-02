"""
apps/accounts/models.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- CustomUser extending AbstractUser
- password_changed field to force password change on first login
- Prevents reverse accessor clashes
- New users start with password_changed = False
- All user-facing text must be in English
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """Extendable user model for THERESE"""

    password_changed = models.BooleanField(
        default=False,
        verbose_name="Password Changed"
    )
    first_login_welcome_shown = models.BooleanField(
        default=False,
        verbose_name="First Login Welcome Popup Shown"
    )

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.get_full_name() or self.username


class LoginPopupConfig(models.Model):
    """Configurable popups or notifications shown at login based on triggers."""

    TRIGGER_CHOICES = [
        ('first_login', 'First login (welcome / profile completion)'),
        ('contract_ending_soon', 'Own contract ending in X months'),
        ('any_contract_ending_soon', 'Any employee contract ending in X months'),
        ('new_task_assigned', 'New task assigned to the user'),
        ('task_status_changed', 'Status changed on a task created by the user'),
        ('login_after_datetime', 'Login after specific date/time'),
    ]

    REACTION_CHOICES = [
        ('popup', 'Show Popup'),
        # ('email', 'Send Email'),  # for future
    ]

    LINK_CHOICES = [
        ('', 'Just OK (no redirect)'),
        ('my_profile', 'My Profile'),
        ('my_tasks', 'My Tasks'),
        ('employee_list', 'Employees List'),
        ('psp_elements', 'PSP Elements'),
        ('workgroup_list', 'Working Groups'),
        ('location_management', 'Manage Locations'),
    ]

    name = models.CharField(max_length=100, unique=True)
    trigger = models.CharField(max_length=50, choices=TRIGGER_CHOICES)
    reaction_type = models.CharField(max_length=20, choices=REACTION_CHOICES, default='popup')
    text = models.TextField(help_text="Message text for popup or email.")
    link_to = models.CharField(max_length=50, choices=LINK_CHOICES, blank=True, help_text="For popup: where to redirect on OK.")
    x_months = models.PositiveIntegerField(null=True, blank=True, help_text="For 'contract_ending_soon' or 'any_contract_ending_soon' trigger.")
    trigger_datetime = models.DateTimeField(null=True, blank=True, help_text="For 'login_after_datetime' trigger.")
    enabled = models.BooleanField(default=True)
    shown_to_users = models.ManyToManyField(
        CustomUser,
        related_name='shown_login_popups',
        blank=True,
        verbose_name="Shown to users",
        help_text="Users who have already seen this popup.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Login Popup Config"
        verbose_name_plural = "Login Popup Configs"

    def __str__(self):
        return f"{self.name} - {self.get_trigger_display()}"


# Prevent reverse accessor clashes
CustomUser.groups.field.remote_field.related_name = 'customuser_groups'
CustomUser.user_permissions.field.remote_field.related_name = 'customuser_user_permissions'


