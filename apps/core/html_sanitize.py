"""Sanitize rich HTML from managers before storing / rendering."""

from __future__ import annotations

try:
    import bleach
except ImportError:  # pragma: no cover
    bleach = None


ALLOWED_TAGS = [
    'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'div', 'em', 'h1', 'h2', 'h3',
    'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'pre', 'span', 'strong',
    'sub', 'sup', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
]
ALLOWED_ATTRIBUTES = {
    '*': ['class'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
}
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


def sanitize_html(value: str | None) -> str:
    """Strip scripts and dangerous markup; return empty string for None."""
    if not value:
        return ''
    if bleach is None:
        # Fail closed-ish: strip tags if bleach missing.
        from django.utils.html import strip_tags
        return strip_tags(value)
    return bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
