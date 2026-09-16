"""Built-in Extern workgroup and its generic PI employee."""

from django.contrib.auth.models import Group

EXTERN_WORKGROUP_SHORT_NAME = 'Extern'
EXTERN_WORKGROUP_LONG_NAME = 'Extern'
EXTERN_PI_FIRST_NAME = 'Extern'
EXTERN_PI_LAST_NAME = 'Externssohn'


def workgroup_is_extern(workgroup) -> bool:
    return bool(
        workgroup and getattr(workgroup, 'short_name', None) == EXTERN_WORKGROUP_SHORT_NAME
    )


def employee_is_extern_pi(employee) -> bool:
    return bool(
        employee
        and getattr(employee, 'is_external', False)
        and getattr(employee, 'first_name', None) == EXTERN_PI_FIRST_NAME
        and getattr(employee, 'last_name', None) == EXTERN_PI_LAST_NAME
    )


def exclude_extern_pi(queryset):
    return queryset.exclude(
        first_name=EXTERN_PI_FIRST_NAME,
        last_name=EXTERN_PI_LAST_NAME,
        is_external=True,
    )


def exclude_extern_workgroup(queryset, *, field='work_group'):
    return queryset.exclude(**{f'{field}__short_name': EXTERN_WORKGROUP_SHORT_NAME})


def ensure_extern_defaults():
    """
    Create the Extern workgroup and PI employee if they are missing.

    Idempotent. Returns (workgroup, employee).
    """
    from apps.hr.models import Employee, Workgroup
    from apps.hr.workgroup_groups import sync_auth_group_for_workgroup

    employee = Employee.objects.filter(
        first_name=EXTERN_PI_FIRST_NAME,
        last_name=EXTERN_PI_LAST_NAME,
        is_external=True,
    ).first()
    if employee is None:
        employee = Employee.objects.create(
            first_name=EXTERN_PI_FIRST_NAME,
            last_name=EXTERN_PI_LAST_NAME,
            is_external=True,
        )
    if employee.user_id:
        employee.user = None
        employee.save(update_fields=['user'])

    workgroup = Workgroup.objects.filter(short_name=EXTERN_WORKGROUP_SHORT_NAME).first()
    if workgroup is None:
        workgroup = Workgroup.objects.create(
            short_name=EXTERN_WORKGROUP_SHORT_NAME,
            long_name=EXTERN_WORKGROUP_LONG_NAME,
            pi=employee,
        )
    if workgroup.members.filter(pk=employee.pk).exists():
        workgroup.members.remove(employee)
    if not workgroup.auth_group_id:
        from django.core.exceptions import ValidationError
        try:
            sync_auth_group_for_workgroup(workgroup)
        except ValidationError:
            group, _ = Group.objects.get_or_create(name=EXTERN_WORKGROUP_SHORT_NAME)
            if workgroup.auth_group_id != group.pk:
                workgroup.auth_group = group
                workgroup.save(update_fields=['auth_group'])
    return workgroup, employee
