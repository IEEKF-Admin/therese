from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.admin import GroupAdmin, UserAdmin


class ThereseAdminSite(admin.AdminSite):
    site_header = "THERESE Administration"
    site_title = "THERESE Admin"
    index_title = "Übersicht"

    def has_permission(self, request):
        # Erlaubt aktive Superuser auch ohne is_staff=True
        # (nützlich für Fresh-Installs mit createsuperuser)
        # Erlaube Zugriff für User mit Management-Permissions
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.is_staff:
            return True
        # Check for any of the new management permissions
        management_perms = [
            'hr.manage_employee',
            'hr.manage_working_group',
            'hr.manage_location',
            'finances.manage_psp_element',
            'tasks.manage_standard_order',
        ]
        return any(request.user.has_perm(perm) for perm in management_perms)


therese_admin = ThereseAdminSite(name="therese_admin")

# Groups und Permissions im custom Admin verfügbar machen
# (wichtig, damit man Gruppen und Berechtigungen im Admin pflegen kann)
therese_admin.register(Group, GroupAdmin)
therese_admin.register(Permission)
from apps.accounts.models import LoginPopupConfig
therese_admin.register(LoginPopupConfig)
