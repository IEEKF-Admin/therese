"""Background send of contract-window trigger emails while the web server runs."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 60 * 60
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
    while True:
        _run_due_contract_emails()
        time.sleep(INTERVAL_SECONDS)


def start_contract_email_scheduler():
    """Start a daemon thread that sends due contract emails about once an hour."""
    global _started
    if _started or not should_start_scheduler():
        return
    _started = True
    thread = threading.Thread(
        target=_loop,
        name='therese-contract-emails',
        daemon=True,
    )
    thread.start()
    logger.info(
        'Contract-ending email scheduler started (every %s seconds).',
        INTERVAL_SECONDS,
    )
