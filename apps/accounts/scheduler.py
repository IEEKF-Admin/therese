"""Background send of due trigger emails while the web server runs."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

SCHEDULE_INTERVAL_SECONDS = 60
CONTRACT_INTERVAL_SECONDS = 60 * 60
STARTUP_DELAY_SECONDS = 60
_started = False


def should_start_scheduler(argv=None):
    """True only for the live web process, not tests or management commands."""
    if os.environ.get('THERESE_DISABLE_SCHEDULER') == '1':
        return False
    if os.environ.get('PYTEST_CURRENT_TEST'):
        return False
    argv = list(argv if argv is not None else sys.argv)
    skip = {
        'test', 'migrate', 'makemigrations', 'shell', 'collectstatic',
        'ensure_groups', 'send_due_trigger_emails', 'createsuperuser',
    }
    if any(part in skip for part in argv):
        return False
    if 'runserver' in argv:
        return os.environ.get('RUN_MAIN') == 'true'
    executable = os.path.basename(argv[0]).lower() if argv else ''
    return executable in {'gunicorn', 'uwsgi', 'daphne', 'hypercorn'}


def _run_due_scheduled_emails():
    from django.db import close_old_connections

    from apps.accounts.trigger_emails import send_due_scheduled_emails

    close_old_connections()
    try:
        sent = send_due_scheduled_emails()
        if sent:
            logger.info('Scheduled trigger emails sent: %s', sent)
    except Exception:
        logger.exception('Scheduled trigger emails failed')
    finally:
        close_old_connections()


def _run_due_contract_emails():
    from django.db import close_old_connections

    from apps.accounts.trigger_emails import send_due_contract_emails

    close_old_connections()
    try:
        sent = send_due_contract_emails()
        if sent:
            logger.info('Contract-ending trigger emails sent: %s', sent)
    except Exception:
        logger.exception('Scheduled contract-ending trigger emails failed')
    finally:
        close_old_connections()


def _loop():
    time.sleep(STARTUP_DELAY_SECONDS)
    last_contract = 0
    while True:
        _run_due_scheduled_emails()
        now = time.time()
        if now - last_contract >= CONTRACT_INTERVAL_SECONDS:
            _run_due_contract_emails()
            last_contract = now
        time.sleep(SCHEDULE_INTERVAL_SECONDS)


def start_trigger_email_scheduler():
    """Start a daemon thread for scheduled and contract-window trigger emails."""
    global _started
    if _started or not should_start_scheduler():
        return
    _started = True
    thread = threading.Thread(
        target=_loop,
        name='therese-trigger-emails',
        daemon=True,
    )
    thread.start()
    logger.info(
        'Trigger email scheduler started (schedule every %s s, contracts every %s s).',
        SCHEDULE_INTERVAL_SECONDS,
        CONTRACT_INTERVAL_SECONDS,
    )


start_contract_email_scheduler = start_trigger_email_scheduler
