"""
Login popup trigger evaluation and acknowledgement tracking.
"""

from datetime import date, timedelta

from django.utils import timezone

from apps.accounts.models import LoginPopupAcknowledgement, LoginPopupConfig

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


def render_popup_text(text, user, employee, contract=None):
    if not employee:
        return text

    first = getattr(user, 'first_name', '') or getattr(employee, 'first_name', '')
    last = getattr(user, 'last_name', '') or getattr(employee, 'last_name', '')
    full = (first + ' ' + last).strip() or str(employee)
    emp_no = getattr(employee, 'employee_number', '')

    contract_end = ''
    if contract and contract.valid_until:
        contract_end = contract.valid_until.strftime('%d.%m.%Y')
    else:
        latest_contract = employee.contracts.filter(valid_until__isnull=False).order_by('-valid_until').first()
        if latest_contract:
            contract_end = latest_contract.valid_until.strftime('%d.%m.%Y')

    today_str = date.today().strftime('%d.%m.%Y')
    replacements = {
        '{{ first_name }}': first,
        '{{ last_name }}': last,
        '{{ full_name }}': full,
        '{{ employee_number }}': emp_no,
        '{{ contract_end }}': contract_end,
        '{{ today }}': today_str,
        '{{ title }}': 'THERESE',
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text


def _should_show_global_trigger(user, config, acknowledged):
    return LoginPopupAcknowledgement.GLOBAL_REFERENCE not in acknowledged


def evaluate_login_popups(user, *, employee=None, assigned_to_me=None, my_created=None):
    """
    Evaluate enabled popup configs for a user after login.
    Returns list of dicts: {'text', 'link', 'config', 'ack_reference_keys'}.
    """
    assigned_to_me = assigned_to_me or []
    my_created = my_created or []
    now = timezone.now()
    popups = []

    configs = (
        LoginPopupConfig.objects.filter(enabled=True)
        .prefetch_related('target_users', 'target_workgroups', 'target_groups')
        .order_by('id')
    )

    for config in configs:
        if not user_matches_audience(user, config):
            continue

        acknowledged = get_acknowledged_reference_keys(user, config)
        show = False
        ack_reference_keys = []
        contract_for_text = None

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

        elif config.trigger == 'new_task_assigned' and employee:
            if user.last_login and _should_show_global_trigger(user, config, acknowledged):
                for task in assigned_to_me:
                    created_at = getattr(task, 'created_at', None)
                    if created_at and created_at > user.last_login:
                        show = True
                        ack_reference_keys = [LoginPopupAcknowledgement.GLOBAL_REFERENCE]
                        break

        elif config.trigger == 'task_status_changed' and employee:
            if user.last_login and _should_show_global_trigger(user, config, acknowledged):
                for task in my_created:
                    updated_at = getattr(task, 'updated_at', None)
                    if updated_at and updated_at > user.last_login:
                        show = True
                        ack_reference_keys = [LoginPopupAcknowledgement.GLOBAL_REFERENCE]
                        break

        elif config.trigger == 'task_comment_on_created_task' and employee:
            if user.last_login:
                from apps.tasks.models import TaskComment
                from apps.tasks.task_protocol import ENTRY_USER_MESSAGE

                task_pks = set(
                    TaskComment.objects.filter(
                        task__creator=employee,
                        entry_type=ENTRY_USER_MESSAGE,
                        created_at__gt=user.last_login,
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

        elif config.trigger == 'login_after_datetime' and config.trigger_datetime:
            if now > config.trigger_datetime and _should_show_global_trigger(user, config, acknowledged):
                show = True
                ack_reference_keys = [LoginPopupAcknowledgement.GLOBAL_REFERENCE]

        elif config.trigger == 'checklist_assigned' and employee:
            from apps.checklists.models import ChecklistInstance

            qs = ChecklistInstance.objects.filter(
                subject=employee,
                status__in=ChecklistInstance.ACTIVE_STATUSES,
            ).select_related('template_version', 'template_version__template')
            if user.last_login:
                qs = qs.filter(assigned_at__gt=user.last_login)
            unacked_refs = [
                f'checklist:{inst.pk}'
                for inst in qs.order_by('-assigned_at')
                if f'checklist:{inst.pk}' not in acknowledged
            ]
            if unacked_refs:
                show = True
                ack_reference_keys = unacked_refs

        if show:
            popups.append({
                'text': render_popup_text(config.text, user, employee, contract=contract_for_text),
                'link': config.link_to or '',
                'config': config,
                'ack_reference_keys': ack_reference_keys,
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