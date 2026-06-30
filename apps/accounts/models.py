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

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.get_full_name() or self.username


# Prevent reverse accessor clashes
CustomUser.groups.field.remote_field.related_name = 'customuser_groups'
CustomUser.user_permissions.field.remote_field.related_name = 'customuser_user_permissions'


