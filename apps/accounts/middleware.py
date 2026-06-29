"""
apps/accounts/middleware.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Forces users with password_changed=False to change their password on first login
- Redirects early, before permission checks
- Skips redirect for password change page itself and logout
- Works even if user has limited permissions
"""

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


class ForcePasswordChangeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Skip for unauthenticated users, static files, media, etc.
        if not request.user.is_authenticated:
            return None

        # Skip if user has already changed password
        if getattr(request.user, 'password_changed', True):
            return None

        # Skip password change page and logout
        password_change_path = reverse('accounts:force_password_change')
        if request.path in [password_change_path, reverse('accounts:logout'), '/admin/logout/']:
            return None

        # Force redirect to password change
        return redirect('accounts:force_password_change')

    def process_response(self, request, response):
        return response