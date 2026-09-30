"""WordPress THERESE Sync REST client (HTTPS Basic, application password)."""

from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HTTP_TIMEOUT = 30
API_PREFIX = '/wp-json/therese/v1'


class WordPressError(Exception):
    def __init__(self, message, status=None, body=''):
        super().__init__(message)
        self.status = status
        self.body = body or ''


def site_base_url(url: str) -> str:
    return (url or '').strip().rstrip('/')


def require_https(url: str) -> str:
    base = site_base_url(url)
    if not base.lower().startswith('https://'):
        raise WordPressError('WordPress site URL must use HTTPS.')
    return base


def _basic_auth_header(username: str, password: str) -> str:
    import base64

    token = base64.b64encode(
        f'{username}:{password}'.encode('utf-8')
    ).decode('ascii')
    return f'Basic {token}'


def _multipart_body(fields: dict, files: dict | None):
    import uuid

    boundary = uuid.uuid4().hex
    body = bytearray()
    for key, value in (fields or {}).items():
        if value is None:
            continue
        body.extend(f'--{boundary}\r\n'.encode('ascii'))
        body.extend(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode('utf-8')
        )
        body.extend(str(value).encode('utf-8'))
        body.extend(b'\r\n')
    for key, item in (files or {}).items():
        if not item:
            continue
        filename, content, content_type = item
        filename = (filename or 'picture').replace('"', '')
        content_type = content_type or 'application/octet-stream'
        body.extend(f'--{boundary}\r\n'.encode('ascii'))
        body.extend(
            (
                f'Content-Disposition: form-data; name="{key}"; '
                f'filename="{filename}"\r\n'
            ).encode('utf-8')
        )
        body.extend(f'Content-Type: {content_type}\r\n\r\n'.encode('ascii'))
        body.extend(content)
        body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode('ascii'))
    return bytes(body), f'multipart/form-data; boundary={boundary}'


def _parse_error(raw: bytes, status: int) -> str:
    text = (raw or b'').decode('utf-8', errors='replace').strip()
    if not text:
        return f'WordPress request failed ({status}).'
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text[:500]
    if isinstance(data, dict):
        message = data.get('message') or data.get('code') or ''
        if message:
            return str(message)
    return text[:500]


def request_json(site, method, path, *, fields=None, files=None, query=None):
    base = require_https(site.url)
    username = (site.username or '').strip()
    password = (site.application_password or '').strip()
    if not username or not password:
        raise WordPressError('WordPress user and application password are required.')
    url = base + API_PREFIX + path
    if query:
        url = url + '?' + urlencode(query)
    headers = {
        'Authorization': _basic_auth_header(username, password),
        'Accept': 'application/json',
        'User-Agent': 'THERESE',
    }
    data = None
    if method != 'GET':
        data, content_type = _multipart_body(fields or {}, files)
        headers['Content-Type'] = content_type
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT, context=ssl.create_default_context()) as resp:
            raw = resp.read()
            status = getattr(resp, 'status', 200)
    except HTTPError as exc:
        raw = exc.read() if exc.fp else b''
        raise WordPressError(_parse_error(raw, exc.code), status=exc.code, body=raw.decode('utf-8', errors='replace')) from exc
    except URLError as exc:
        raise WordPressError(f'Could not reach WordPress: {exc.reason}') from exc
    if status >= 400:
        raise WordPressError(_parse_error(raw, status), status=status, body=raw.decode('utf-8', errors='replace'))
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode('utf-8'))
    except json.JSONDecodeError as exc:
        raise WordPressError(f'WordPress returned invalid JSON: {exc}') from exc
    return parsed


def probe_wordpress_connection(site) -> dict:
    data = request_json(site, 'GET', '/status')
    if not data.get('ok'):
        raise WordPressError('WordPress status check did not return ok.')
    return data


def create_wordpress_post(site, fields: dict, picture=None) -> dict:
    files = {'picture': picture} if picture else None
    return request_json(site, 'POST', '/posts', fields=fields, files=files)


def update_wordpress_post(site, posttitle: str, fields: dict, picture=None) -> dict:
    payload = dict(fields or {})
    payload['posttitle'] = posttitle
    files = {'picture': picture} if picture else None
    return request_json(site, 'POST', '/posts/update', fields=payload, files=files)


def unpublish_wordpress_post(site, posttitle: str) -> dict:
    return request_json(site, 'POST', '/posts/unpublish', fields={'posttitle': posttitle})
