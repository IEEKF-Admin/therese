"""Send trigger emails when the event happens, not when the user next logs in."""

import logging
from datetime import date, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from apps.accounts.login_popups import user_matches_audience
from apps.accounts.models import LoginPopupConfig, TriggerEmailSend
from apps.accounts.template_variables import (
    build_replacement_map,
    recipient_email,
    render_placeholders,
)
from apps.core.mail import send_therese_html_email

logger = logging.getLogger(__name__)

LOGIN_TIME_TRIGGERS = frozenset({
    'first_login',
    'login_after_datetime',
})


def _employee_of(user):
    if user is None:
        return None
    try:
        return user.employee
    except (AttributeError, ObjectDoesNotExist):
        return None


def user_for_employee(employee):
    if employee is None:
        return None
    user = getattr(employee, 'user', None)
    if user is None or not getattr(user, 'is_active', False):
        return None
    return user


def enabled_email_configs(trigger):
    return list(
        LoginPopupConfig.objects.filter(
            enabled=True,
            send_email=True,
            trigger=trigger,
        ).prefetch_related('target_users', 'target_workgroups', 'target_groups')
    )


def contract_in_window(contract, x_months):
    if not contract or not contract.valid_until or not x_months:
        return False
    today = date.today()
    cutoff = today + timedelta(days=x_months * 30)
    return today <= contract.valid_until <= cutoff


def deliver_trigger_email(config, user, employee, reference_key, **context):
    """Send one email if the config, audience, template, and dedupe checks pass."""
    if config is None or not config.send_email or not config.enabled:
        return False
    if user is None or not user.is_active:
        return False
    if not user_matches_audience(user, config):
        return False
    if TriggerEmailSend.objects.filter(
        config=config, user=user, reference_key=reference_key
    ).exists():
        return False
    html_template = (config.email_html or '').strip()
    if not html_template:
        return False
    to_email = recipient_email(user, employee)
    if not to_email:
        logger.warning(
            'Trigger email skipped for config %s: no recipient for user %s',
            config.pk,
            user.pk,
        )
        return False
    replacements = build_replacement_map(
        user,
        employee,
        contract=context.get('contract'),
        task=context.get('task'),
        checklist=context.get('checklist'),
        chemical_item=context.get('chemical_item'),
        comment=context.get('comment'),
    )
    subject = render_placeholders(
        config.email_subject or config.name,
        replacements,
        html=False,
        user=user,
        employee=employee,
    )
    html_body = render_placeholders(
        html_template,
        replacements,
        html=True,
        user=user,
        employee=employee,
    )
    try:
        send_therese_html_email(to_email, subject, html_body)
    except Exception:
        logger.exception(
            'Trigger email failed for config %s user %s',
            config.pk,
            user.pk,
        )
        return False
    TriggerEmailSend.objects.get_or_create(
        config=config,
        user=user,
        reference_key=reference_key,
    )
    return True


def notify_subject(trigger, user, employee, reference_key, **context):
    if user is None:
        return
    for config in enabled_email_configs(trigger):
        deliver_trigger_email(config, user, employee, reference_key, **context)


def send_login_time_trigger_emails(user, employee=None):
    """first_login and login_after_datetime still fire when the user logs in."""
    if user is None:
        return
    if employee is None:
        employee = _employee_of(user)
    now = timezone.now()

    if not getattr(user, 'first_login_welcome_shown', False):
        notify_subject('first_login', user, employee, 'global')

    for config in enabled_email_configs('login_after_datetime'):
        if config.trigger_datetime and now > config.trigger_datetime:
            deliver_trigger_email(config, user, employee, 'global')


def notify_audience(trigger, reference_key, **context):
    """Send a trigger email to every active user in the config audience."""
    from apps.accounts.models import CustomUser

    users = list(CustomUser.objects.filter(is_active=True))
    for config in enabled_email_configs(trigger):
        for user in users:
            deliver_trigger_email(
                config,
                user,
                _employee_of(user),
                reference_key,
                **context,
            )


PERSONNEL_CREATED_TYPES = (
    'personnel_reallocation',
    'personnel_contract_extension',
    'personnel_recruitment',
)


def notify_task_created(task):
    if task is None:
        return
    task_type = getattr(task, 'task_type', '') or ''
    if task_type == 'purchase_order':
        notify_audience(
            'purchase_order_created',
            f'po_created:{task.pk}',
            task=task,
        )
    elif task_type in PERSONNEL_CREATED_TYPES:
        notify_audience(
            'personnel_task_created',
            f'personnel_created:{task.pk}',
            task=task,
        )


def notify_task_assigned(task):
    employee = getattr(task, 'assignee', None)
    user = user_for_employee(employee)
    if user is None:
        return
    notify_subject(
        'new_task_assigned',
        user,
        employee,
        f'task_assigned:{task.pk}:{employee.pk}',
        task=task,
    )


def notify_task_status_changed(task, previous_status):
    employee = getattr(task, 'creator', None)
    user = user_for_employee(employee)
    if user is None:
        return
    new_status = task.status or ''
    old_status = previous_status or ''
    notify_subject(
        'task_status_changed',
        user,
        employee,
        f'task_status:{task.pk}:{old_status}:{new_status}'[:191],
        task=task,
    )


def notify_task_comment(comment):
    if comment is None:
        return
    from apps.tasks.models import TaskComment

    if comment.entry_type != TaskComment.ENTRY_USER_MESSAGE:
        return
    task = comment.task
    creator = getattr(task, 'creator', None)
    if creator is None or comment.author_id == creator.pk:
        return
    user = user_for_employee(creator)
    if user is None:
        return
    notify_subject(
        'task_comment_on_created_task',
        user,
        creator,
        f'task_comment:{comment.pk}',
        task=task,
        comment=comment,
    )


def notify_checklist_assigned(instance):
    employee = getattr(instance, 'subject', None)
    user = user_for_employee(employee)
    if user is None:
        return
    notify_subject(
        'checklist_assigned',
        user,
        employee,
        f'checklist:{instance.pk}',
        checklist=instance,
    )


def notify_chemical_item_incomplete(item):
    employee = getattr(item, 'ordered_by', None)
    user = user_for_employee(employee)
    if user is None:
        return
    notify_subject(
        'chemical_item_incomplete',
        user,
        employee,
        f'chemical_item:{item.pk}',
        chemical_item=item,
    )


def notify_chemical_item_delivered(item):
    employee = getattr(item, 'ordered_by', None)
    user = user_for_employee(employee)
    if user is None:
        return
    notify_subject(
        'chemical_item_delivered',
        user,
        employee,
        f'chemical_delivered:{item.pk}',
        chemical_item=item,
    )


def notify_contract_ending(contract):
    if contract is None:
        return
    employee = getattr(contract, 'employee', None)
    holder_user = user_for_employee(employee)
    reference_key = f'contract:{contract.pk}'

    for config in enabled_email_configs('contract_ending_soon'):
        if not contract_in_window(contract, config.x_months):
            continue
        if holder_user is not None:
            deliver_trigger_email(
                config, holder_user, employee, reference_key, contract=contract
            )

    from apps.accounts.models import CustomUser

    audience_users = list(CustomUser.objects.filter(is_active=True))
    for config in enabled_email_configs('any_contract_ending_soon'):
        if not contract_in_window(contract, config.x_months):
            continue
        for user in audience_users:
            deliver_trigger_email(
                config,
                user,
                _employee_of(user),
                reference_key,
                contract=contract,
            )


def send_due_contract_emails():
    """Send for contracts currently in an X-months window (e.g. daily command)."""
    from apps.hr.models import Contract

    today = date.today()
    sent = 0
    for config in enabled_email_configs('contract_ending_soon'):
        if not config.x_months:
            continue
        cutoff = today + timedelta(days=config.x_months * 30)
        contracts = Contract.objects.filter(
            valid_until__isnull=False,
            valid_until__gte=today,
            valid_until__lte=cutoff,
        ).select_related('employee', 'employee__user')
        for contract in contracts:
            employee = contract.employee
            user = user_for_employee(employee)
            if user is None:
                continue
            if deliver_trigger_email(
                config, user, employee, f'contract:{contract.pk}', contract=contract
            ):
                sent += 1
    from apps.accounts.models import CustomUser

    audience_users = list(CustomUser.objects.filter(is_active=True))
    for config in enabled_email_configs('any_contract_ending_soon'):
        if not config.x_months:
            continue
        cutoff = today + timedelta(days=config.x_months * 30)
        contracts = Contract.objects.filter(
            valid_until__isnull=False,
            valid_until__gte=today,
            valid_until__lte=cutoff,
        ).select_related('employee', 'employee__user')
        for contract in contracts:
            for user in audience_users:
                if deliver_trigger_email(
                    config,
                    user,
                    _employee_of(user),
                    f'contract:{contract.pk}',
                    contract=contract,
                ):
                    sent += 1
    return sent
