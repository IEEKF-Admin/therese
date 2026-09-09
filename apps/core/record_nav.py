"""Previous/next record URLs for edit screens."""

from __future__ import annotations

from django.urls import reverse


def adjacent_pks(ordered_queryset, current_pk) -> tuple[int | None, int | None]:
    ids = list(ordered_queryset.values_list('pk', flat=True))
    try:
        idx = ids.index(current_pk)
    except ValueError:
        return None, None
    prev_pk = ids[idx - 1] if idx > 0 else None
    next_pk = ids[idx + 1] if idx + 1 < len(ids) else None
    return prev_pk, next_pk


def adjacent_item_urls(ordered_queryset, current_pk, url_name: str) -> tuple[str, str]:
    prev_pk, next_pk = adjacent_pks(ordered_queryset, current_pk)
    prev_url = reverse(url_name, args=[prev_pk]) if prev_pk else ''
    next_url = reverse(url_name, args=[next_pk]) if next_pk else ''
    return prev_url, next_url
