from django.contrib import admin


class ThereseAdminSite(admin.AdminSite):
    site_header = "THERESE Administration"
    site_title = "THERESE Admin"
    index_title = "Übersicht"

    def has_permission(self, request):
        # Erlaubt aktive Superuser auch ohne is_staff=True
        # (nützlich für Fresh-Installs mit createsuperuser)
        return request.user.is_active and (
            request.user.is_staff or request.user.is_superuser
        )


therese_admin = ThereseAdminSite(name="therese_admin")
