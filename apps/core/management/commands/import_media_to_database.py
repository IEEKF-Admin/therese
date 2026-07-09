"""
Import files from the legacy MEDIA_ROOT directory into database storage.

Run once after switching to DatabaseStorage when existing files still live on disk.
"""

from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from apps.core.models import StoredFile


class Command(BaseCommand):
    help = 'Import files from MEDIA_ROOT into StoredFile records (database storage).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List files that would be imported without writing to the database.',
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stdout.write(self.style.WARNING(f'MEDIA_ROOT does not exist: {media_root}'))
            return

        imported = 0
        skipped = 0

        for file_path in sorted(media_root.rglob('*')):
            if not file_path.is_file():
                continue

            relative = file_path.relative_to(media_root).as_posix()
            if StoredFile.objects.filter(name=relative).exists():
                skipped += 1
                continue

            if options['dry_run']:
                self.stdout.write(f'Would import: {relative}')
                imported += 1
                continue

            with file_path.open('rb') as handle:
                django_file = File(handle, name=file_path.name)
                default_storage.save(relative, django_file)
            imported += 1
            self.stdout.write(f'Imported: {relative}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. imported={imported} skipped={skipped} dry_run={options["dry_run"]}'
        ))