"""Google Calendar ACL helpers (OAuth as calendar owner, share with Gmail users)."""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'
GOOGLE_CALENDAR_URL = 'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}'
GOOGLE_ACL_URL = 'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/acl'
HTTP_TIMEOUT = 20
CALENDAR_ROLE = 'writer'
OAUTH_SCOPES = (
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/userinfo.email',
)


class GoogleCalendarError(Exception):
    def __init__(self, message, status=None, body=''):
        super().__init__(message)
        self.status = status
        self.body = body or ''


def _oauth_setting():
    from apps.core.models import GlobalSetting

    return GlobalSetting.get_solo()


def oauth_client_id(setting=None) -> str:
    env = (getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '') or '').strip()
    if env:
        return env
    setting = setting or _oauth_setting()
    return (getattr(setting, 'google_oauth_client_id', '') or '').strip()


def oauth_client_secret(setting=None) -> str:
    env = (getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '') or '').strip()
    if env:
        return env
    setting = setting or _oauth_setting()
    return (getattr(setting, 'google_oauth_client_secret', '') or '').strip()


def oauth_configured(setting=None) -> bool:
    if setting is None:
        return bool(oauth_client_id() and oauth_client_secret())
    return bool(oauth_client_id(setting) and oauth_client_secret(setting))


def oauth_redirect_uri(request) -> str:
    path = reverse('core_settings:google_calendar_callback')
    site = (getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')
    if site:
        return site + path
    return request.build_absolute_uri(path)


def oauth_authorize_url(request, state: str) -> str:
    params = {
        'client_id': oauth_client_id(),
        'redirect_uri': oauth_redirect_uri(request),
        'response_type': 'code',
        'scope': ' '.join(OAUTH_SCOPES),
        'access_type': 'offline',
        'prompt': 'select_account consent',
        'include_granted_scopes': 'true',
        'state': state,
    }
    return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'


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


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    payload = _http_json(
        'POST',
        GOOGLE_TOKEN_URL,
        data={
            'code': code,
            'client_id': oauth_client_id(),
            'client_secret': oauth_client_secret(),
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        },
    )
    access = payload.get('access_token') or ''
    if access and not payload.get('email'):
        try:
            info = _http_json(
                'GET',
                GOOGLE_USERINFO_URL,
                headers={'Authorization': f'Bearer {access}'},
            )
            payload['email'] = (info.get('email') or '').strip()
        except GoogleCalendarError:
            logger.warning('Could not read Google userinfo after OAuth', exc_info=True)
    return payload


def refresh_access_token(refresh_token: str) -> str:
    payload = _http_json(
        'POST',
        GOOGLE_TOKEN_URL,
        data={
            'client_id': oauth_client_id(),
            'client_secret': oauth_client_secret(),
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        },
    )
    token = (payload.get('access_token') or '').strip()
    if not token:
        raise GoogleCalendarError('Google did not return an access token.')
    return token


def revoke_token(token: str) -> None:
    if not (token or '').strip():
        return
    try:
        _http_json('POST', GOOGLE_REVOKE_URL, data={'token': token})
    except GoogleCalendarError as exc:
        if exc.status not in (400, 404):
            raise


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


class HttpCalendarClient:
    def __init__(self, setting=None, access_token=None):
        from apps.core.models import GlobalSetting

        self.setting = setting or GlobalSetting.get_solo()
        self.calendar_id = (self.setting.google_calendar_id or '').strip()
        if not self.calendar_id:
            raise GoogleCalendarError('Google Calendar ID is not set.')
        token = (self.setting.google_calendar_refresh_token or '').strip()
        if not token:
            raise GoogleCalendarError('Google Calendar is not connected.')
        self.access_token = access_token or refresh_access_token(token)

    def share(self, email: str, role: str = CALENDAR_ROLE) -> None:
        insert_acl(self.calendar_id, self.access_token, email, role)

    def unshare(self, email: str) -> None:
        delete_acl(self.calendar_id, self.access_token, email)


def get_calendar_client(setting=None):
    return HttpCalendarClient(setting)


def _calendar_url(calendar_id: str) -> str:
    return GOOGLE_CALENDAR_URL.format(calendar_id=quote(calendar_id, safe=''))


def probe_calendar_connection(setting=None) -> dict:
    """Refresh the token, load the calendar, and confirm ACL can be read."""
    from apps.core.models import GlobalSetting

    setting = setting or GlobalSetting.get_solo()
    calendar_id = (setting.google_calendar_id or '').strip()
    if not calendar_id:
        raise GoogleCalendarError('Google Calendar ID is not set.')
    token = (setting.google_calendar_refresh_token or '').strip()
    if not token:
        raise GoogleCalendarError('Google Calendar is not connected.')
    access = refresh_access_token(token)
    headers = _auth_headers(access)
    calendar = _http_json('GET', _calendar_url(calendar_id), headers=headers)
    try:
        _http_json('GET', _acl_url(calendar_id) + '?maxResults=1', headers=headers)
    except GoogleCalendarError as exc:
        if exc.status == 403:
            raise GoogleCalendarError(
                'Calendar is reachable, but this Google account cannot manage '
                'sharing. Sign in as the calendar owner.'
            ) from exc
        raise
    return {
        'id': (calendar.get('id') or calendar_id).strip(),
        'summary': (calendar.get('summary') or '').strip(),
    }
