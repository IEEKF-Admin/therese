"""Send time-window trigger emails (contract ending in X months).

Run daily, e.g. from Windows Task Scheduler:
  python manage.py send_due_trigger_emails
"""

from django.core.management.base import BaseCommand

from apps.accounts.trigger_emails import send_due_contract_emails


class Command(BaseCommand):
    help = (
        'Send trigger emails for contracts currently ending within the configured '
        'X-months window. Event-based triggers (tasks, comments, checklists, chemicals) '
        'are sent immediately and are not handled here.'
    )

    def handle(self, *args, **options):
        sent = send_due_contract_emails()
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} due trigger email(s).'))
