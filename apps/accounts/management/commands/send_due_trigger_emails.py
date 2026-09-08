"""Send time-window trigger emails (schedule + contract ending in X months).

Run daily, e.g. from Windows Task Scheduler:
  python manage.py send_due_trigger_emails
"""

from django.core.management.base import BaseCommand

from apps.accounts.trigger_emails import send_due_contract_emails, send_due_scheduled_emails


class Command(BaseCommand):
    help = (
        'Send due recurring-schedule emails and contract-ending emails. '
        'The web server already polls the schedule about once a minute and '
        'contract windows about once an hour; this command is a manual fallback. '
        'Event-based triggers (tasks, comments, checklists, chemicals) are sent '
        'immediately and are not handled here.'
    )

    def handle(self, *args, **options):
        scheduled = send_due_scheduled_emails()
        contracts = send_due_contract_emails()
        sent = scheduled + contracts
        self.stdout.write(
            self.style.SUCCESS(
                f'Sent {sent} due trigger email(s) '
                f'({scheduled} scheduled, {contracts} contract-ending).'
            )
        )
