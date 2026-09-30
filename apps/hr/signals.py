"""
apps/hr/signals.py

Robust automatic creation of CustomUser for new Employees.
New employees' users are added to the baseline "Employee" group.

Pending / check_needed employees (e.g. from funding-report import) do not
get a login user until those flags are cleared.
"""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver
import logging

from .models import Building, Contract, Employee, Room, WordPressSite, Workgroup
from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames

logger = logging.getLogger(__name__)


def ensure_employee_group_membership(user):
    """Add user to the baseline Employee group (idempotent)."""
    if user is None:
        return
    group, _ = Group.objects.get_or_create(name=GroupNames.EMPLOYEE)
    user.groups.add(group)


def _should_create_login_user(employee: Employee) -> bool:
    """Login users only when the employee is not pending and not check_needed."""
    if getattr(employee, 'is_external', False):
        return False
    if getattr(employee, 'is_pending', False):
        return False
    if getattr(employee, 'check_needed', False):
        return False
    return True


@receiver(post_save, sender=Employee)
def create_user_for_employee(sender, instance, created, **kwargs):
    if not created:
        # When flags are cleared later, do not auto-create a user here —
        # linking/creating login users remains a deliberate admin action.
        return

    if not _should_create_login_user(instance):
        logger.info(
            "Skipping auto user for pending/check_needed employee %s",
            instance.employee_number,
        )
        return

    created_user = None
    created_password = None
    try:
        with transaction.atomic():
            if not instance.user_id:
                first = (instance.first_name or "").strip().lower()
                last = (instance.last_name or "").strip().lower()

                base_username = (
                    f"{first}{last[0]}"
                    if first and last
                    else f"emp_{instance.employee_number or instance.pk}"
                )
                username = base_username
                counter = 1
                while CustomUser.objects.filter(username=username).exists():
                    username = (
                        f"{base_username}{last[:counter] if last else str(counter)}"
                    )
                    counter += 1
                    if counter > 15:
                        username = f"emp_{instance.pk}"
                        break

                from apps.accounts.account_emails import (
                    generate_random_password,
                    send_account_email,
                )
                from apps.accounts.models import AccountEmailTemplate

                password = generate_random_password()
                user = CustomUser.objects.create_user(
                    username=username,
                    first_name=instance.first_name or "",
                    last_name=instance.last_name or "",
                    email=instance.email_professional or instance.email_private or "",
                    password=password,
                )

                user.is_active = True
                user.is_staff = True
                user.password_changed = False
                user.save(update_fields=['is_active', 'is_staff', 'password_changed'])

                instance.user = user
                instance.save(update_fields=['user'])

                logger.info(f"Staff user created: {username} for {instance}")
                created_password = password
                created_user = user

            # Baseline role: every new employee gets the Employee group
            ensure_employee_group_membership(instance.user)

        if created_user is not None and created_password:
            send_account_email(
                AccountEmailTemplate.KIND_USER_CREATED,
                created_user,
                instance,
                created_password,
            )

    except Exception as e:
        logger.error(f"Error creating user for {instance}: {e}", exc_info=True)


def _schedule_google_calendar(employee_id):
    from apps.hr.provisioning import schedule_google_calendar_sync

    schedule_google_calendar_sync(employee_id)


@receiver(post_save, sender=Employee)
def sync_google_calendar_for_employee(sender, instance, created, update_fields, **kwargs):
    if not created and update_fields is not None and 'google_account' not in update_fields:
        return
    _schedule_google_calendar(instance.pk)


@receiver(post_save, sender=Contract)
@receiver(post_delete, sender=Contract)
def sync_google_calendar_for_contract(sender, instance, **kwargs):
    _schedule_google_calendar(instance.employee_id)


@receiver(pre_delete, sender=Employee)
def unshare_google_calendar_on_employee_delete(sender, instance, **kwargs):
    from apps.hr.provisioning import unshare_employee_google_calendar

    unshare_employee_google_calendar(instance)


def _schedule_sympa(employee_id):
    from apps.hr.provisioning import schedule_sympa_sync

    schedule_sympa_sync(employee_id)


@receiver(post_save, sender=Employee)
def sync_sympa_for_employee(sender, instance, created, update_fields, **kwargs):
    if not created and update_fields is not None and 'email_professional' not in update_fields:
        return
    _schedule_sympa(instance.pk)


@receiver(post_save, sender=Contract)
@receiver(post_delete, sender=Contract)
def sync_sympa_for_contract(sender, instance, **kwargs):
    _schedule_sympa(instance.employee_id)


@receiver(pre_delete, sender=Employee)
def unsubscribe_sympa_on_employee_delete(sender, instance, **kwargs):
    from apps.hr.provisioning import unsubscribe_employee_sympa

    unsubscribe_employee_sympa(instance)


@receiver(m2m_changed, sender=Workgroup.members.through)
def sync_sympa_for_workgroup_members(sender, instance, action, pk_set, **kwargs):
    if action == 'pre_clear':
        instance._sympa_cleared_pks = list(instance.members.values_list('pk', flat=True))
        return
    if action == 'post_clear':
        pks = getattr(instance, '_sympa_cleared_pks', [])
    elif action in ('post_add', 'post_remove'):
        pks = pk_set or []
    else:
        return
    for pk in pks:
        _schedule_sympa(pk)


@receiver(post_save, sender=Workgroup)
def sync_sympa_for_workgroup_list(sender, instance, update_fields, **kwargs):
    if update_fields is not None and 'sympa_list' not in update_fields:
        return
    for pk in instance.members.values_list('pk', flat=True):
        _schedule_sympa(pk)


_WP_EMPLOYEE_FIELDS = {
    'first_name',
    'last_name',
    'employee_number',
    'website',
    'phone_number',
    'private_phone_number',
    'email_professional',
    'profile_picture',
    'room',
}


def _scan_wordpress_employee(employee):
    from apps.hr.wordpress import scan_employee_wordpress

    scan_employee_wordpress(employee)


@receiver(post_save, sender=Employee)
def scan_wordpress_for_employee(sender, instance, created, update_fields, **kwargs):
    if created:
        return
    if update_fields is not None and not (_WP_EMPLOYEE_FIELDS & set(update_fields)):
        return
    _scan_wordpress_employee(instance)


@receiver(post_save, sender=Building)
def scan_wordpress_for_building(sender, instance, update_fields, **kwargs):
    if update_fields is not None and 'address' not in update_fields:
        return
    from apps.hr.wordpress import scan_employees_for_building

    scan_employees_for_building(instance)


@receiver(post_save, sender=Room)
def scan_wordpress_for_room(sender, instance, update_fields, **kwargs):
    if update_fields is not None and 'building' not in update_fields:
        return
    for employee in Employee.objects.filter(room=instance).iterator():
        _scan_wordpress_employee(employee)


@receiver(m2m_changed, sender=Workgroup.members.through)
def scan_wordpress_for_workgroup_members(sender, instance, action, pk_set, **kwargs):
    if isinstance(instance, Employee):
        if action in ('post_add', 'post_remove', 'post_clear'):
            _scan_wordpress_employee(instance)
        return
    if not isinstance(instance, Workgroup):
        return
    if action == 'pre_clear':
        instance._wp_cleared_pks = list(instance.members.values_list('pk', flat=True))
        return
    if action == 'post_clear':
        pks = getattr(instance, '_wp_cleared_pks', [])
    elif action in ('post_add', 'post_remove'):
        pks = pk_set or []
    else:
        return
    for employee in Employee.objects.filter(pk__in=pks).iterator():
        _scan_wordpress_employee(employee)


@receiver(m2m_changed, sender=WordPressSite.workgroups.through)
def scan_wordpress_for_site_workgroups(sender, instance, action, pk_set, **kwargs):
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return
    from apps.hr.wordpress import scan_wordpress_site

    if isinstance(instance, WordPressSite):
        scan_wordpress_site(instance)
        return
    if pk_set:
        for site in WordPressSite.objects.filter(pk__in=pk_set):
            scan_wordpress_site(site)
