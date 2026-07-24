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

from django.contrib.auth.models import AbstractUser, Group
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
        (
            'task_comment_on_created_task',
            'New message on a task created by the user (by someone else)',
        ),
        ('login_after_datetime', 'Login after specific date/time'),
        ('checklist_assigned', 'New checklist assigned to the user'),
        (
            'chemical_item_incomplete',
            'Chemicals: own chemical item missing required inventory data',
        ),
        (
            'chemical_item_delivered',
            'Chemicals: own chemical item was delivered (complete inventory data)',
        ),
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
        ('my_checklists', 'My Checklists'),
        ('chemical_items', 'Chemicals - My Chemical Items'),
        ('chemical_undelivered', 'Undelivered Order Items (all POs)'),
    ]

    AUDIENCE_MATCH_CHOICES = [
        ('or', 'OR — match any selected criterion'),
        ('and', 'AND — match all selected criteria'),
    ]

    name = models.CharField(max_length=100, unique=True)
    trigger = models.CharField(max_length=50, choices=TRIGGER_CHOICES)
    reaction_type = models.CharField(max_length=20, choices=REACTION_CHOICES, default='popup')
    text = models.TextField(help_text="Message text for popup or email.")
    link_to = models.CharField(max_length=50, choices=LINK_CHOICES, blank=True, help_text="For popup: where to redirect on OK.")
    x_months = models.PositiveIntegerField(null=True, blank=True, help_text="For 'contract_ending_soon' or 'any_contract_ending_soon' trigger.")
    trigger_datetime = models.DateTimeField(null=True, blank=True, help_text="For 'login_after_datetime' trigger.")
    enabled = models.BooleanField(default=True)
    audience_match_mode = models.CharField(
        max_length=3,
        choices=AUDIENCE_MATCH_CHOICES,
        default='or',
        verbose_name="Audience match mode",
        help_text="How user, work group, and Django group targets are combined.",
    )
    target_users = models.ManyToManyField(
        CustomUser,
        related_name='targeted_login_popups',
        blank=True,
        verbose_name="Target users",
        help_text="If set, only these users see this popup (combined with other targets below).",
    )
    target_workgroups = models.ManyToManyField(
        'hr.Workgroup',
        related_name='targeted_login_popups',
        blank=True,
        verbose_name="Target work groups",
        help_text="If set, members of these work groups also see this popup.",
    )
    target_groups = models.ManyToManyField(
        Group,
        related_name='targeted_login_popups',
        blank=True,
        verbose_name="Target Django groups",
        help_text="If set, users in these Django groups also see this popup.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Login Popup Config"
        verbose_name_plural = "Login Popup Configs"

    def __str__(self):
        return f"{self.name} - {self.get_trigger_display()}"

    def has_audience_restrictions(self):
        if self.pk:
            return (
                self.target_users.exists()
                or self.target_workgroups.exists()
                or self.target_groups.exists()
            )
        return False


class LoginPopupAcknowledgement(models.Model):
    """Tracks which popup conditions a user has already confirmed."""

    GLOBAL_REFERENCE = 'global'

    config = models.ForeignKey(
        LoginPopupConfig,
        on_delete=models.CASCADE,
        related_name='acknowledgements',
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='login_popup_acknowledgements',
    )
    reference_key = models.CharField(
        max_length=64,
        help_text="'global' for one-time triggers, or 'contract:<pk>' per contract.",
    )
    shown_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Login Popup Acknowledgement"
        verbose_name_plural = "Login Popup Acknowledgements"
        constraints = [
            models.UniqueConstraint(
                fields=['config', 'user', 'reference_key'],
                name='unique_login_popup_ack',
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.config.name} — {self.reference_key}"

    @classmethod
    def contract_reference(cls, contract):
        return f'contract:{contract.pk}'

    @classmethod
    def task_comment_reference(cls, task):
        return f'task_comment:{task.pk}'


# Prevent reverse accessor clashes
CustomUser.groups.field.remote_field.related_name = 'customuser_groups'
CustomUser.user_permissions.field.remote_field.related_name = 'customuser_user_permissions'


