"""Sanitize rich HTML from managers before storing / rendering."""

from __future__ import annotations

try:
    import bleach
except ImportError:  # pragma: no cover
    bleach = None


ALLOWED_TAGS = [
    'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'div', 'em', 'h1', 'h2', 'h3',
    'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'pre', 's', 'span',
    'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
]
ALLOWED_ATTRIBUTES = {
    '*': ['class', 'style'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
}
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']
ALLOWED_CSS_PROPERTIES = [
    'background-color',
    'border',
    'border-collapse',
    'color',
    'font-family',
    'font-size',
    'font-style',
    'font-weight',
    'height',
    'margin',
    'padding',
    'text-align',
    'text-decoration',
    'vertical-align',
    'width',
]


def sanitize_html(value: str | None) -> str:
    """Strip scripts and dangerous markup; return empty string for None."""
    if not value:
        return ''
    if bleach is None:
        # Fail closed-ish: strip tags if bleach missing.
        from django.utils.html import strip_tags
        return strip_tags(value)
    clean_kwargs = {
        'tags': ALLOWED_TAGS,
        'attributes': ALLOWED_ATTRIBUTES,
        'protocols': ALLOWED_PROTOCOLS,
        'strip': True,
    }
    try:
        from bleach.css_sanitizer import CSSSanitizer
    except ImportError:  # pragma: no cover
        CSSSanitizer = None
    if CSSSanitizer is not None:
        clean_kwargs['css_sanitizer'] = CSSSanitizer(
            allowed_css_properties=ALLOWED_CSS_PROPERTIES,
        )
    return bleach.clean(value, **clean_kwargs)
