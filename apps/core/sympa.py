"""Sympa owner commands via SMTP (no SOAP/REST)."""

from __future__ import annotations

import ssl

from django.conf import settings
from django.core.mail import EmailMessage

from apps.core.mail import get_from_email, get_mail_connection, mail_configured, mail_params


class SympaError(Exception):
    pass


def normalize_list_address(value: str) -> str:
    return (value or '').strip().lower()


def list_name(address: str) -> str:
    value = normalize_list_address(address)
    if '@' in value:
        return value.split('@', 1)[0]
    return value


def subscriber_gecos(employee) -> str:
    parts = [
        (getattr(employee, 'first_name', '') or '').strip(),
        (getattr(employee, 'last_name', '') or '').strip(),
    ]
    return ' '.join(part for part in parts if part)


def quiet_add(list_address: str, email: str, gecos: str = '') -> str:
    name = list_name(list_address)
    line = f'QUIET ADD {name} {email}'
    extra = (gecos or '').replace('\n', ' ').replace('\r', ' ').strip()
    if extra:
        line = f'{line} {extra}'
    return line


def quiet_delete(list_address: str, email: str) -> str:
    return f'QUIET DELETE {list_name(list_address)} {email}'


def send_sympa_commands(commands, setting=None) -> None:
    from apps.core.models import GlobalSetting

    setting = setting or GlobalSetting.get_solo()
    robot = (setting.sympa_robot or '').strip()
    if not robot:
        raise SympaError('Sympa robot address is not set.')
    if not mail_configured(setting):
        raise SympaError('Outbound email From address is not set.')
    backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').strip()
    if 'smtp.EmailBackend' in backend and not mail_params(setting)['host']:
        raise SympaError('SMTP host is not set.')
    lines = [str(item).strip() for item in commands if str(item).strip()]
    if not lines:
        return
    message = EmailMessage(
        subject='THERESE mailing list update',
        body='\n'.join(lines) + '\n',
        from_email=get_from_email(setting) or None,
        to=[robot],
        connection=get_mail_connection(setting),
    )
    try:
        message.send(fail_silently=False)
    except (ssl.SSLError, OSError) as exc:
        text = str(exc)
        if 'WRONG_VERSION_NUMBER' in text or 'wrong version number' in text.lower():
            raise SympaError(
                'SMTP TLS mismatch: implicit SSL on a port that speaks plain SMTP. '
                'Use port 465 with SSL, or 587 with STARTTLS.'
            ) from exc
        raise


def probe_sympa_connection(setting=None) -> None:
    """Send HELP so operators can verify the robot mailbox accepts mail."""
    send_sympa_commands(['HELP'], setting)
