"""Sync Django auth groups with HR workgroups."""

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError


def sync_auth_group_for_workgroup(workgroup, *, old_short_name=None):
    """
    Ensure a Django Group exists for the workgroup short_name.
    Renames the linked group when short_name changes.
    """
    if workgroup.auth_group_id:
        group = workgroup.auth_group
        if group.name != workgroup.short_name:
            if Group.objects.filter(name=workgroup.short_name).exclude(pk=group.pk).exists():
                raise ValidationError(
                    f'A Django group named "{workgroup.short_name}" already exists.'
                )
            group.name = workgroup.short_name
            group.save(update_fields=['name'])
        return group

    existing = Group.objects.filter(name=workgroup.short_name).first()
    if existing:
        linked = getattr(existing, 'workgroup', None)
        if linked is not None and linked.pk != workgroup.pk:
            raise ValidationError(
                f'A Django group named "{workgroup.short_name}" is already linked to another workgroup.'
            )
        group = existing
    else:
        group = Group.objects.create(name=workgroup.short_name)

    workgroup.auth_group = group
    workgroup.save(update_fields=['auth_group'])
    return group