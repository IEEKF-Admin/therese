"""Safe HTTP helpers (redirects, Content-Disposition)."""

from __future__ import annotations

from urllib.parse import quote

from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect(request, target, *, fallback='/'):
    """
    Redirect only to same-host relative URLs (open-redirect safe).
    """
    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return HttpResponseRedirect(target)
    return HttpResponseRedirect(resolve_url(fallback))


def content_disposition(filename: str, *, as_attachment: bool = True) -> str:
    """RFC 5987-friendly Content-Disposition without header injection."""
    safe_name = (filename or 'download').replace('\r', '').replace('\n', '').replace('"', '')
    disposition = 'attachment' if as_attachment else 'inline'
    # ASCII fallback + UTF-8 filename*
    ascii_name = safe_name.encode('ascii', 'ignore').decode('ascii') or 'download'
    utf8_name = quote(safe_name)
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
