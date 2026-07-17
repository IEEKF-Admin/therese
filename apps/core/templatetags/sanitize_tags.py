from django import template
from django.utils.safestring import mark_safe

from apps.core.html_sanitize import sanitize_html

register = template.Library()


@register.filter(name='sanitize_html')
def sanitize_html_filter(value):
    """Sanitize HTML then mark safe for intentional rich-text rendering."""
    return mark_safe(sanitize_html(value))
