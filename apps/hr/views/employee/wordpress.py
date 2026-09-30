"""Publish / unpublish employee WordPress posts from the accounts tab."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import user_is_systemadmin
from apps.core.wordpress import WordPressError
from apps.hr.models import Employee, WordPressSite
from apps.hr.wordpress import publish_employee_to_site, unpublish_employee_from_site

TEXT_KEYS = (
    'posttitle',
    'name',
    'linkmember',
    'position',
    'phone',
    'mobile',
    'email',
    'address',
    'websideadressfield',
    'linkfieldaddress',
)


def _accounts_redirect():
    return redirect(reverse('hr:employee_accounts'))


@login_required
@require_POST
def wordpress_publish(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied
    employee = get_object_or_404(
        Employee.objects.select_related('room__building').prefetch_related('workgroups'),
        pk=request.POST.get('employee'),
    )
    site = get_object_or_404(
        WordPressSite.objects.prefetch_related('workgroups'),
        pk=request.POST.get('site'),
    )
    fields = {key: request.POST.get(key, '') for key in TEXT_KEYS}
    picture = request.FILES.get('picture')
    try:
        publish_employee_to_site(employee, site, fields, picture_upload=picture)
    except WordPressError as exc:
        messages.error(request, f'WordPress ({site.name}): {exc}')
        return _accounts_redirect()
    messages.success(
        request,
        f'Published {employee.last_name}, {employee.first_name} on {site.name}.',
    )
    return _accounts_redirect()


@login_required
@require_POST
def wordpress_unpublish(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=request.POST.get('employee'))
    site = get_object_or_404(WordPressSite, pk=request.POST.get('site'))
    try:
        unpublish_employee_from_site(employee, site)
    except WordPressError as exc:
        messages.error(request, f'WordPress ({site.name}): {exc}')
        return _accounts_redirect()
    messages.success(
        request,
        f'Unpublished {employee.last_name}, {employee.first_name} on {site.name} (draft).',
    )
    return _accounts_redirect()
