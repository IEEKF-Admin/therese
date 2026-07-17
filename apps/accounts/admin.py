"""
apps/accounts/admin.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Admin interface for CustomUser
- All user-facing text must be in English
- Header block must be maintained and only extended when new requirements are explicitly added

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from therese.admin import therese_admin

from .models import CustomUser


@admin.register(CustomUser, site=therese_admin)
class CustomUserAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
        (
            _('Permissions'),
            {
                'fields': (
                    'is_active',
                    'is_staff',
                    'is_superuser',
                    'groups',
                    'user_permissions',
                ),
            },
        ),
        (
            _('THERESE flags'),
            {
                'fields': ('password_changed', 'first_login_welcome_shown'),
                'description': _(
                    'Password Changed = user already completed the forced first-login password change.'
                ),
            },
        ),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    readonly_fields = ('last_login', 'date_joined')
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'is_staff',
        'is_active',
        'password_changed',
    )
    list_filter = (
        'is_staff',
        'is_superuser',
        'is_active',
        'password_changed',
        'groups',
    )

