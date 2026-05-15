from django import template

register = template.Library()

# Reihenfolge der Stati (wichtig für "nur vorwärts")
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
    """Gibt die Position des Status zurück (für Vergleich vorwärts/nur höher)"""
    try:
        return STATUS_ORDER.index(status)
    except ValueError:
        return 999  # unbekannter Status