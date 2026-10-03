"""Explicit operator-controlled database transfer; never runs at startup."""
import json
import os

from django.core.management.base import BaseCommand, CommandError

from apps.common.database_transfer import (
    digest, export_archive, import_archive, manifest, snapshot, validate_archive,
)


class Command(BaseCommand):
    help = 'Export/import/verify business data across database engines; archives contain sensitive data.'

    def add_arguments(self, parser):
        parser.add_argument('operation', choices=['export', 'import', 'verify'])
        parser.add_argument('--file', required=True)
        parser.add_argument('--database', default='default')
        parser.add_argument('--confirm-source-writes-frozen', action='store_true')

    def handle(self, *args, **options):
        operation = options['operation']
        using = options['database']
        path = options['file']
        if operation == 'export':
            if not options['confirm_source_writes_frozen']:
                raise CommandError('Freeze source writes and back up MySQL/media first; then confirm explicitly.')
            archive = export_archive(using)
            # Fail if it exists. Never accidentally overwrite the last backup.
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except OSError as exc:
                raise CommandError(f'Cannot create archive: {exc}') from exc
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(archive, stream, ensure_ascii=False)
            self.stdout.write(self.style.SUCCESS(
                f'Exported {len(archive["records"])} records; keep archive private.'
            ))
            return
        try:
            with open(path, encoding='utf-8') as stream:
                archive = json.load(stream)
        except (OSError, ValueError) as exc:
            raise CommandError(f'Cannot read archive: {exc}') from exc
        validate_archive(archive)
        if operation == 'import':
            import_archive(archive, using)
        else:
            restored = snapshot(using)
            if digest(restored) != archive['sha256'] or manifest(restored) != archive['manifest']:
                raise CommandError('Database does not exactly match the source archive.')
        for label, row in archive['manifest'].items():
            self.stdout.write(f'{label}: {row["count"]} records verified')
        self.stdout.write(self.style.SUCCESS(
            'Counts, serialized values and relationships verified.'
        ))
