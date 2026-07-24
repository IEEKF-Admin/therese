"""Signals for chemicals ↔ purchase items."""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='tasks.PurchaseItem')
def purchase_item_sync_chemical(sender, instance, **kwargs):
    # Avoid circular import / migration issues
    try:
        from apps.chemicals.services import sync_purchase_item_chemical
        sync_purchase_item_chemical(instance)
    except Exception:
        # Never break PO save if chemical lookup fails
        import logging
        logging.getLogger(__name__).exception(
            'Chemical sync failed for PurchaseItem pk=%s', instance.pk
        )
