from django import template

register = template.Library()

# Status order (used for "only forward" status logic)
STATUS_ORDER = [
    'noch nicht bearbeitet',
    'bearbeitet und in Abstimmung',
    'bearbeitet und bei der Verwaltung bestellt',
    'beim Lieferanten bestellt',
    'im Lager angekommen',
    'geliefert'
]


@register.filter
def status_index(status):
    """Returns the position of the status (for forward-only comparisons)."""
    try:
        return STATUS_ORDER.index(status)
    except ValueError:
        return 999  # unknown status


@register.filter
def standard_item_exists(item, supplier):
    """
    Template filter used in PO detail views.
    Returns True if a StandardPurchaseItem already exists for this supplier + item.order_number.
    Used to hide the "Mark as Standard" checkbox for Approvers when the item is already in the catalog.
    """
    from apps.tasks.models import StandardPurchaseItem
    if not item or not supplier:
        return False
    order_number = getattr(item, 'order_number', '') or ''
    return StandardPurchaseItem.already_exists(supplier, order_number)


