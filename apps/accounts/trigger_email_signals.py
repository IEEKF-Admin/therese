"""Fire trigger emails from model events (not from login)."""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _task_models():
    from apps.tasks.models import Task

    models = [Task]
    pending = list(Task.__subclasses__())
    while pending:
        model = pending.pop()
        if model in models:
            continue
        models.append(model)
        pending.extend(model.__subclasses__())
    return models


def cache_task_previous_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._trigger_prev_assignee_id = None
        instance._trigger_prev_status = None
        return
    from apps.tasks.models import Task

    prev = Task.objects.filter(pk=instance.pk).values('assignee_id', 'status').first()
    instance._trigger_prev_assignee_id = prev['assignee_id'] if prev else None
    instance._trigger_prev_status = prev['status'] if prev else None


def send_task_trigger_emails(sender, instance, created, **kwargs):
    try:
        from apps.accounts.trigger_emails import notify_task_assigned, notify_task_status_changed

        prev_assignee_id = getattr(instance, '_trigger_prev_assignee_id', None)
        if instance.assignee_id and (created or instance.assignee_id != prev_assignee_id):
            notify_task_assigned(instance)

        prev_status = getattr(instance, '_trigger_prev_status', None)
        if not created and instance.status and instance.status != prev_status:
            notify_task_status_changed(instance, prev_status)
    except Exception:
        logger.exception('Task trigger email dispatch failed for pk=%s', instance.pk)


def register_task_email_signals():
    """Django MTI saves do not emit Task signals; connect concrete subclasses."""
    for model in _task_models():
        pre_save.connect(
            cache_task_previous_state,
            sender=model,
            dispatch_uid=f'trigger_email_task_pre_{model._meta.label}',
        )
        post_save.connect(
            send_task_trigger_emails,
            sender=model,
            dispatch_uid=f'trigger_email_task_post_{model._meta.label}',
        )


@receiver(post_save, sender='tasks.TaskComment')
def send_task_comment_trigger_emails(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from apps.accounts.trigger_emails import notify_task_comment

        notify_task_comment(instance)
    except Exception:
        logger.exception('Comment trigger email dispatch failed for pk=%s', instance.pk)


@receiver(post_save, sender='checklists.ChecklistInstance')
def send_checklist_assigned_trigger_emails(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from apps.accounts.trigger_emails import notify_checklist_assigned

        notify_checklist_assigned(instance)
    except Exception:
        logger.exception('Checklist trigger email dispatch failed for pk=%s', instance.pk)


@receiver(pre_save, sender='chemicals.ChemicalItem')
def cache_chemical_item_previous_state(sender, instance, **kwargs):
    instance._trigger_prev_incomplete = False
    instance._trigger_prev_status = None
    if not instance.pk:
        return
    from apps.chemicals.models import ChemicalItem

    prev = ChemicalItem.objects.filter(pk=instance.pk).select_related('chemical').first()
    if prev is None:
        return
    instance._trigger_prev_incomplete = prev.is_incomplete
    instance._trigger_prev_status = prev.status


@receiver(post_save, sender='chemicals.ChemicalItem')
def send_chemical_item_trigger_emails(sender, instance, created, **kwargs):
    try:
        from apps.accounts.trigger_emails import (
            notify_chemical_item_delivered,
            notify_chemical_item_incomplete,
        )
        from apps.chemicals.models import ChemicalItem

        was_incomplete = getattr(instance, '_trigger_prev_incomplete', False)
        if instance.is_incomplete and (created or not was_incomplete):
            notify_chemical_item_incomplete(instance)

        prev_status = getattr(instance, '_trigger_prev_status', None)
        became_delivered = instance.status == ChemicalItem.Status.ACTIVE and (
            created or prev_status != ChemicalItem.Status.ACTIVE
        )
        if became_delivered:
            notify_chemical_item_delivered(instance)
    except Exception:
        logger.exception('Chemical trigger email dispatch failed for pk=%s', instance.pk)


@receiver(post_save, sender='hr.Contract')
def send_contract_ending_trigger_emails(sender, instance, **kwargs):
    try:
        from apps.accounts.trigger_emails import notify_contract_ending

        notify_contract_ending(instance)
    except Exception:
        logger.exception('Contract trigger email dispatch failed for pk=%s', instance.pk)
