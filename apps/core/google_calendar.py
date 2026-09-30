"""Google Calendar ACL helpers (service account, share with Gmail users)."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from django.conf import settings

GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_CALENDAR_URL = 'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}'
GOOGLE_ACL_URL = 'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/acl'
HTTP_TIMEOUT = 20
CALENDAR_ROLE = 'writer'
CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar'
JWT_GRANT = 'urn:ietf:params:oauth:grant-type:jwt-bearer'


class GoogleCalendarError(Exception):
    def __init__(self, message, status=None, body=''):
        super().__init__(message)
        self.status = status
        self.body = body or ''


def _setting():
    from apps.core.models import GlobalSetting

    return GlobalSetting.get_solo()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def parse_service_account_json(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GoogleCalendarError(f'Service account JSON is invalid: {exc}') from exc
    if not isinstance(data, dict):
        raise GoogleCalendarError('Service account JSON must be an object.')
    email = (data.get('client_email') or '').strip()
    key = (data.get('private_key') or '').strip()
    if not email or not key:
        raise GoogleCalendarError('Service account JSON must contain client_email and private_key.')
    return data


def service_account_raw(setting=None) -> str:
    env_json = (getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_JSON', '') or '').strip()
    if env_json:
        return env_json
    env_file = (getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', '') or '').strip()
    if env_file:
        try:
            return Path(env_file).read_text(encoding='utf-8')
        except OSError as exc:
            raise GoogleCalendarError(f'Could not read service account file: {exc}') from exc
    setting = setting or _setting()
    return (getattr(setting, 'google_service_account_json', '') or '').strip()


def service_account_info(setting=None) -> dict:
    raw = service_account_raw(setting)
    if not raw:
        return {}
    return parse_service_account_json(raw)


def service_account_email(setting=None) -> str:
    try:
        info = service_account_info(setting)
    except GoogleCalendarError:
        setting = setting or _setting()
        return (getattr(setting, 'google_service_account_email', '') or '').strip()
    return (info.get('client_email') or '').strip()


def service_account_configured(setting=None) -> bool:
    try:
        info = service_account_info(setting)
    except GoogleCalendarError:
        return False
    return bool((info.get('client_email') or '').strip() and (info.get('private_key') or '').strip())


def _service_account_jwt(info: dict) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    email = (info.get('client_email') or '').strip()
    pem = (info.get('private_key') or '').strip()
    now = int(time.time())
    header = _b64url(json.dumps({'alg': 'RS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    payload = _b64url(json.dumps({
        'iss': email,
        'sub': email,
        'aud': GOOGLE_TOKEN_URL,
        'iat': now,
        'exp': now + 3600,
        'scope': CALENDAR_SCOPE,
    }, separators=(',', ':')).encode())
    signing_input = f'{header}.{payload}'.encode('ascii')
    try:
        key = serialization.load_pem_private_key(pem.encode('utf-8'), password=None)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        raise GoogleCalendarError(f'Service account private key is invalid: {exc}') from exc
    return f'{header}.{payload}.{_b64url(signature)}'


def service_account_access_token(setting=None) -> str:
    info = service_account_info(setting)
    if not info:
        raise GoogleCalendarError('Google service account JSON is not set.')
    payload = _http_json(
        'POST',
        GOOGLE_TOKEN_URL,
        data={
            'grant_type': JWT_GRANT,
            'assertion': _service_account_jwt(info),
        },
    )
    token = (payload.get('access_token') or '').strip()
    if not token:
        raise GoogleCalendarError('Google did not return an access token.')
    return token


def _http_json(method, url, *, data=None, json_body=None, headers=None):
    hdrs = dict(headers or {})
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode('utf-8')
        hdrs.setdefault('Content-Type', 'application/json')
    elif data is not None:
        body = urlencode(data).encode('utf-8')
        hdrs.setdefault('Content-Type', 'application/x-www-form-urlencoded')
    req = Request(url, data=body, headers=hdrs, method=method)
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode('utf-8'))
    except HTTPError as exc:
        err_body = exc.read().decode('utf-8', errors='replace')
        raise GoogleCalendarError(
            f'Google API {exc.code}: {err_body}',
            status=exc.code,
            body=err_body,
        ) from exc
    except URLError as exc:
        raise GoogleCalendarError(f'Google API unreachable: {exc}') from exc
    except json.JSONDecodeError as exc:
        raise GoogleCalendarError(f'Google API returned invalid JSON: {exc}') from exc


def _acl_url(calendar_id: str, rule_id: str | None = None) -> str:
    base = GOOGLE_ACL_URL.format(calendar_id=quote(calendar_id, safe=''))
    if rule_id:
        return f'{base}/{quote(rule_id, safe="")}'
    return base


def _auth_headers(access_token: str) -> dict:
    return {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
    }


def acl_rule_id(email: str) -> str:
    return f'user:{(email or "").strip().lower()}'


def insert_acl(calendar_id: str, access_token: str, email: str, role: str = CALENDAR_ROLE) -> None:
    email = (email or '').strip().lower()
    if not email:
        raise GoogleCalendarError('Missing Google account address.')
    try:
        _http_json(
            'POST',
            _acl_url(calendar_id) + '?sendNotifications=true',
            json_body={
                'role': role,
                'scope': {'type': 'user', 'value': email},
            },
            headers=_auth_headers(access_token),
        )
    except GoogleCalendarError as exc:
        if exc.status == 409:
            return
        raise


def delete_acl(calendar_id: str, access_token: str, email: str) -> None:
    email = (email or '').strip().lower()
    if not email:
        return
    try:
        _http_json(
            'DELETE',
            _acl_url(calendar_id, acl_rule_id(email)) + '?sendNotifications=false',
            headers=_auth_headers(access_token),
        )
    except GoogleCalendarError as exc:
        if exc.status in (404, 410):
            return
        raise


def list_acl_user_emails(calendar_id: str, access_token: str) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()
    page_token = ''
    while True:
        params = {'maxResults': '250'}
        if page_token:
            params['pageToken'] = page_token
        payload = _http_json(
            'GET',
            _acl_url(calendar_id) + '?' + urlencode(params),
            headers=_auth_headers(access_token),
        )
        for item in payload.get('items') or []:
            scope = item.get('scope') or {}
            if (scope.get('type') or '').strip().lower() != 'user':
                continue
            email = (scope.get('value') or '').strip().lower()
            if not email or email in seen:
                continue
            seen.add(email)
            emails.append(email)
        page_token = (payload.get('nextPageToken') or '').strip()
        if not page_token:
            break
    return emails


class HttpCalendarClient:
    def __init__(self, setting=None, access_token=None):
        from apps.core.models import GlobalSetting

        self.setting = setting or GlobalSetting.get_solo()
        self.calendar_id = (self.setting.google_calendar_id or '').strip()
        if not self.calendar_id:
            raise GoogleCalendarError('Google Calendar ID is not set.')
        if not service_account_configured(self.setting):
            raise GoogleCalendarError('Google service account JSON is not set.')
        self.access_token = access_token or service_account_access_token(self.setting)

    def share(self, email: str, role: str = CALENDAR_ROLE) -> None:
        insert_acl(self.calendar_id, self.access_token, email, role)

    def unshare(self, email: str) -> None:
        delete_acl(self.calendar_id, self.access_token, email)

    def list_shared_emails(self) -> list[str]:
        emails = list_acl_user_emails(self.calendar_id, self.access_token)
        sa = (service_account_email(self.setting) or '').strip().lower()
        if not sa:
            return emails
        return [email for email in emails if email != sa]


def get_calendar_client(setting=None):
    return HttpCalendarClient(setting)


def _calendar_url(calendar_id: str) -> str:
    return GOOGLE_CALENDAR_URL.format(calendar_id=quote(calendar_id, safe=''))


def probe_calendar_connection(setting=None) -> dict:
    """Mint a service-account token, load the calendar, and confirm ACL can be read."""
    from apps.core.models import GlobalSetting

    setting = setting or GlobalSetting.get_solo()
    calendar_id = (setting.google_calendar_id or '').strip()
    if not calendar_id:
        raise GoogleCalendarError('Google Calendar ID is not set.')
    if not service_account_configured(setting):
        raise GoogleCalendarError('Google service account JSON is not set.')
    access = service_account_access_token(setting)
    headers = _auth_headers(access)
    calendar = _http_json('GET', _calendar_url(calendar_id), headers=headers)
    try:
        _http_json('GET', _acl_url(calendar_id) + '?maxResults=1', headers=headers)
    except GoogleCalendarError as exc:
        if exc.status == 403:
            email = service_account_email(setting) or 'the service account'
            raise GoogleCalendarError(
                'Calendar is reachable, but the service account cannot manage '
                f'sharing. Share the calendar with {email} as '
                '"Make changes and manage sharing".'
            ) from exc
        raise
    return {
        'id': (calendar.get('id') or calendar_id).strip(),
        'summary': (calendar.get('summary') or '').strip(),
        'email': service_account_email(setting),
    }
