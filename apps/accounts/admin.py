"""
apps/accounts/admin.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Admin interface for CustomUser
- All user-facing text must be in English
- Header block must be maintained and only extended when new requirements are explicitly added

Do not remove any existing requirements from this header without explicit instruction.
"""

from therese.admin import therese_admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@therese_admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    pass


