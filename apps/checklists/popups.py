from django.urls import reverse

from apps.accounts.login_popups import get_acknowledged_reference_keys
from apps.checklists.models import ChecklistInstance


def evaluate_checklist_assigned_popups(user, *, employee=None):
    """Return login popups for new checklist assignments since last login."""
    if not employee:
        return []

    qs = ChecklistInstance.objects.filter(
        subject=employee,
        status__in=ChecklistInstance.ACTIVE_STATUSES,
    ).select_related('template_version', 'template_version__template')

    if user.last_login:
        qs = qs.filter(assigned_at__gt=user.last_login)

    instances = list(qs.order_by('-assigned_at'))
    if not instances:
        return []

    from apps.accounts.models import LoginPopupConfig

    try:
        config = LoginPopupConfig.objects.get(trigger='checklist_assigned', enabled=True)
    except LoginPopupConfig.DoesNotExist:
        config = None

    acknowledged = set()
    if config:
        acknowledged = get_acknowledged_reference_keys(user, config)

    popups = []
    for instance in instances:
        ref = f'checklist:{instance.pk}'
        if ref in acknowledged:
            continue
        template = instance.template_version.template
        popups.append({
            'text': (
                f'A new checklist has been assigned to you: {template.name_en} / '
                f'{template.name_de} ({instance.template_version.version_label}).'
            ),
            'link': 'my_checklists',
            'url': reverse('checklists:instance_fill', args=[instance.pk]),
            'instance_id': instance.pk,
            'ack_reference_keys': [ref],
            'config': config,
        })
    return popups


def persist_checklist_popup_acks(user, popups):
    from apps.accounts.login_popups import acknowledge_popup

    for popup in popups:
        config = popup.get('config')
        if not config:
            continue
        keys = popup.get('ack_reference_keys') or []
        if keys:
            acknowledge_popup(user, config, keys)
