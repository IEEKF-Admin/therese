"""
Login popup trigger evaluation and acknowledgement tracking.
"""

from datetime import date, datetime, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

POPUP_SINCE_SESSION_KEY = 'therese_popup_since'
_SINCE_UNSET = object()

from apps.accounts.models import LoginPopupAcknowledgement, LoginPopupConfig
from apps.accounts.template_variables import (
    build_replacement_map,
    render_placeholders,
)

CONTRACT_TRIGGERS = frozenset({
    'contract_ending_soon',
    'any_contract_ending_soon',
})


def _user_matches_target_users(user, config):
    return config.target_users.filter(pk=user.pk).exists()


def _user_matches_target_groups(user, config):
    if not config.target_groups.exists():
        return False
    user_group_ids = set(user.groups.values_list('pk', flat=True))
    target_group_ids = set(config.target_groups.values_list('pk', flat=True))
    return bool(user_group_ids & target_group_ids)


def _user_matches_target_workgroups(user, config):
    employee = getattr(user, 'employee', None)
    if not employee:
        return False
    return config.target_workgroups.filter(members=employee).exists()


def store_popup_since(request, user):
    """Remember last_login from before Django overwrites it on this login."""
    previous = getattr(user, 'last_login', None)
    request.session[POPUP_SINCE_SESSION_KEY] = previous.isoformat() if previous else ''


def popup_since_from_session(request_or_session):
    """Previous login time, or None on first login / missing session."""
    session = getattr(request_or_session, 'session', request_or_session)
    raw = session.get(POPUP_SINCE_SESSION_KEY)
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def user_matches_audience(user, config):
    """Return True if the popup applies to this user (empty targets = everyone)."""
    if not config.has_audience_restrictions():
        return True

    checks = []
    if config.target_users.exists():
        checks.append(_user_matches_target_users(user, config))
    if config.target_workgroups.exists():
        checks.append(_user_matches_target_workgroups(user, config))
    if config.target_groups.exists():
        checks.append(_user_matches_target_groups(user, config))

    if not checks:
        return True

    if config.audience_match_mode == 'and':
        return all(checks)
    return any(checks)


def get_acknowledged_reference_keys(user, config):
    return set(
        LoginPopupAcknowledgement.objects.filter(
            config=config,
            user=user,
        ).values_list('reference_key', flat=True)
    )


def acknowledge_popup(user, config, reference_keys):
    for key in reference_keys:
        LoginPopupAcknowledgement.objects.get_or_create(
            config=config,
            user=user,
            reference_key=key,
        )


def contracts_ending_within_months(x_months, employee=None):
    from apps.hr.models import Contract

    today = date.today()
    cutoff = today + timedelta(days=x_months * 30)
    qs = Contract.objects.filter(
        valid_until__isnull=False,
        valid_until__gte=today,
        valid_until__lte=cutoff,
    ).select_related('employee')
    if employee is not None:
        qs = qs.filter(employee=employee)
    return qs.order_by('valid_until')


def unacknowledged_contracts(user, config, x_months, employee=None):
    acknowledged = get_acknowledged_reference_keys(user, config)
    return [
        contract
        for contract in contracts_ending_within_months(x_months, employee=employee)
        if LoginPopupAcknowledgement.contract_reference(contract) not in acknowledged
    ]


def render_popup_text(text, user, employee, contract=None, **context):
    replacements = build_replacement_map(
        user,
        employee,
        contract=contract,
        task=context.get('task'),
        checklist=context.get('checklist'),
        chemical_item=context.get('chemical_item'),
        comment=context.get('comment'),
    )
    return render_placeholders(text, replacements, html=False, user=user, employee=employee)


def _should_show_global_trigger(user, config, acknowledged):
    return LoginPopupAcknowledgement.GLOBAL_REFERENCE not in acknowledged


def evaluate_login_popups(
    user,
    *,
    employee=None,
    assigned_to_me=None,
    my_created=None,
    since=_SINCE_UNSET,
):
    """
    Evaluate enabled popup configs for a user after login.
    Returns list of dicts: {'text', 'link', 'config', 'ack_reference_keys'}.

    ``since`` is the previous login time (before Django set last_login to now).
    Omit it in tests to fall back to ``user.last_login``. Pass ``None`` for a
    first login so event-since-last-session popups are skipped.
    """
    assigned_to_me = assigned_to_me or []
    my_created = my_created or []
    now = timezone.now()
    event_since = user.last_login if since is _SINCE_UNSET else since
    popups = []

    configs = (
        LoginPopupConfig.objects.filter(enabled=True)
        .prefetch_related('target_users', 'target_workgroups', 'target_groups')
        .order_by('id')
    )

    for config in configs:
        if not config.show_popup:
            continue
        if not user_matches_audience(user, config):
            continue

        acknowledged = get_acknowledged_reference_keys(user, config)
        show = False
        ack_reference_keys = []
        contract_for_text = None
        task_for_text = None
        checklist_for_text = None
        chemical_for_text = None
        comment_for_text = None

        if config.trigger == 'first_login':
            if user.first_login_welcome_shown:
                continue
            if _should_show_global_trigger(user, config, acknowledged):
                show = True
                ack_reference_keys = [LoginPopupAcknowledgement.GLOBAL_REFERENCE]

        elif config.trigger == 'contract_ending_soon' and config.x_months and employee:
            unacked = unacknowledged_contracts(
                user, config, config.x_months, employee=employee
            )
            if unacked:
                show = True
                contract_for_text = unacked[0]
                ack_reference_keys = [
                    LoginPopupAcknowledgement.contract_reference(c) for c in unacked
                ]

        elif config.trigger == 'any_contract_ending_soon' and config.x_months:
            unacked = unacknowledged_contracts(user, config, config.x_months)
            if unacked:
                show = True
                contract_for_text = unacked[0]
                ack_reference_keys = [
                    LoginPopupAcknowledgement.contract_reference(c) for c in unacked
                ]

        elif config.trigger in ('purchase_order_created', 'personnel_task_created'):
            if event_since:
                from apps.tasks.models import PERSONNEL_TASK_TYPES, PurchaseOrderTask, Task

                if config.trigger == 'purchase_order_created':
                    created_qs = PurchaseOrderTask.objects.filter(
                        created_at__gt=event_since,
                    )
                    ref_prefix = 'po_created'
                else:
                    created_qs = Task.objects.filter(
                        task_type__in=PERSONNEL_TASK_TYPES,
                        created_at__gt=event_since,
                    )
                    ref_prefix = 'personnel_created'
                rows = list(created_qs.order_by('-created_at'))
                unacked_refs = [
                    f'{ref_prefix}:{task.pk}'
                    for task in rows
                    if f'{ref_prefix}:{task.pk}' not in acknowledged
                ]
                if unacked_refs:
                    show = True
                    ack_reference_keys = unacked_refs
                    task_for_text = next(
                        (
                            task for task in rows
                            if f'{ref_prefix}:{task.pk}' in unacked_refs
                        ),
                        None,
                    )

        elif config.trigger == 'new_task_assigned' and employee:
            if event_since:
                unacked = []
                for task in assigned_to_me:
                    created_at = getattr(task, 'created_at', None)
                    ref = f'task_assigned:{task.pk}'
                    if created_at and created_at > event_since and ref not in acknowledged:
                        unacked.append((task, ref))
                if unacked:
                    show = True
                    task_for_text = unacked[0][0]
                    ack_reference_keys = [ref for _task, ref in unacked]

        elif config.trigger == 'task_status_changed' and employee:
            if event_since:
                unacked = []
                for task in my_created:
                    updated_at = getattr(task, 'updated_at', None)
                    ref = f'task_status:{task.pk}:{task.status}'
                    if updated_at and updated_at > event_since and ref not in acknowledged:
                        unacked.append((task, ref))
                if unacked:
                    show = True
                    task_for_text = unacked[0][0]
                    ack_reference_keys = [ref for _task, ref in unacked]

        elif config.trigger == 'task_comment_on_created_task' and employee:
            if event_since:
                from apps.tasks.models import TaskComment
                from apps.tasks.task_protocol import ENTRY_USER_MESSAGE

                task_pks = set(
                    TaskComment.objects.filter(
                        task__creator=employee,
                        entry_type=ENTRY_USER_MESSAGE,
                        created_at__gt=event_since,
                    )
                    .exclude(author=employee)
                    .values_list('task_id', flat=True)
                )
                unacked_refs = [
                    f'task_comment:{task_pk}'
                    for task_pk in task_pks
                    if f'task_comment:{task_pk}' not in acknowledged
                ]
                if unacked_refs:
                    show = True
                    ack_reference_keys = unacked_refs
                    comment_for_text = (
                        TaskComment.objects.filter(
                            task_id__in=task_pks,
                            entry_type=ENTRY_USER_MESSAGE,
                            created_at__gt=event_since,
                        )
                        .exclude(author=employee)
                        .select_related('task', 'author')
                        .order_by('-created_at')
                        .first()
                    )
                    if comment_for_text is not None:
                        task_for_text = comment_for_text.task

        elif config.trigger == 'login_after_datetime' and config.trigger_datetime:
            if now > config.trigger_datetime and _should_show_global_trigger(user, config, acknowledged):
                show = True
                ack_reference_keys = [LoginPopupAcknowledgement.GLOBAL_REFERENCE]

        elif config.trigger == 'checklist_assigned' and employee and event_since:
            from apps.checklists.models import ChecklistInstance

            qs = ChecklistInstance.objects.filter(
                subject=employee,
                status__in=ChecklistInstance.ACTIVE_STATUSES,
            ).select_related('template_version', 'template_version__template')
            if event_since:
                qs = qs.filter(assigned_at__gt=event_since)
            checklist_rows = list(qs.order_by('-assigned_at'))
            unacked_refs = [
                f'checklist:{inst.pk}'
                for inst in checklist_rows
                if f'checklist:{inst.pk}' not in acknowledged
            ]
            if unacked_refs:
                show = True
                ack_reference_keys = unacked_refs
                checklist_for_text = next(
                    (inst for inst in checklist_rows if f'checklist:{inst.pk}' in unacked_refs),
                    None,
                )

        elif config.trigger == 'chemical_item_incomplete' and employee:
            from apps.chemicals.models import ChemicalItem

            qs = ChemicalItem.objects.filter(
                ordered_by=employee,
            ).exclude(status=ChemicalItem.Status.ARCHIVED).select_related('chemical')
            incomplete = [item for item in qs if item.is_incomplete]
            unacked_refs = [
                f'chemical_item:{item.pk}'
                for item in incomplete
                if f'chemical_item:{item.pk}' not in acknowledged
            ]
            if unacked_refs:
                show = True
                ack_reference_keys = unacked_refs
                chemical_for_text = next(
                    (item for item in incomplete if f'chemical_item:{item.pk}' in unacked_refs),
                    None,
                )

        elif config.trigger == 'chemical_item_delivered' and employee and event_since:
            from apps.chemicals.models import ChemicalItem

            qs = ChemicalItem.objects.filter(
                ordered_by=employee,
                status=ChemicalItem.Status.ACTIVE,
            ).select_related('chemical')
            if event_since:
                qs = qs.filter(delivered_at__gt=event_since)
            delivered_rows = list(qs.order_by('-delivered_at'))
            unacked_refs = [
                f'chemical_delivered:{item.pk}'
                for item in delivered_rows
                if f'chemical_delivered:{item.pk}' not in acknowledged
            ]
            if unacked_refs:
                show = True
                ack_reference_keys = unacked_refs
                chemical_for_text = next(
                    (
                        item
                        for item in delivered_rows
                        if f'chemical_delivered:{item.pk}' in unacked_refs
                    ),
                    None,
                )

        if show:
            popups.append({
                'text': render_popup_text(
                    config.text,
                    user,
                    employee,
                    contract=contract_for_text,
                    task=task_for_text,
                    checklist=checklist_for_text,
                    chemical_item=chemical_for_text,
                    comment=comment_for_text,
                ),
                'link': config.link_to or '',
                'config': config,
                'ack_reference_keys': ack_reference_keys,
                'show_popup': config.show_popup,
                'contract': contract_for_text,
                'task': task_for_text,
                'checklist': checklist_for_text,
                'chemical_item': chemical_for_text,
                'comment': comment_for_text,
            })

    return popups


def persist_popup_acknowledgements(user, popups):
    """Store acknowledgements and legacy first-login flag after popups are shown."""
    for popup in popups:
        config = popup['config']
        acknowledge_popup(user, config, popup['ack_reference_keys'])
        if config.trigger == 'first_login':
            user.first_login_welcome_shown = True
            user.save(update_fields=['first_login_welcome_shown'])


def send_login_trigger_emails(user, popups):
    """Send emails only for login-time triggers (first login / after datetime)."""
    from apps.accounts.trigger_emails import LOGIN_TIME_TRIGGERS, deliver_trigger_email

    employee = None
    try:
        employee = user.employee
    except (AttributeError, ObjectDoesNotExist):
        employee = None
    for popup in popups:
        config = popup.get('config')
        if config is None or not config.send_email:
            continue
        if config.trigger not in LOGIN_TIME_TRIGGERS:
            continue
        keys = popup.get('ack_reference_keys') or ['global']
        deliver_trigger_email(
            config,
            user,
            employee,
            keys[0],
            contract=popup.get('contract'),
            task=popup.get('task'),
            checklist=popup.get('checklist'),
            chemical_item=popup.get('chemical_item'),
            comment=popup.get('comment'),
        )