from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from web import backup


class Command(BaseCommand):
    help = 'Replace all of this Osmia\'s data with an export (what is here first goes to data/backups/).'

    def add_arguments(self, parser):
        parser.add_argument('file', help='the export (.zip)')
        parser.add_argument('--yes', action='store_true', help='don\'t ask first')

    def handle(self, file, yes=False, **options):
        if not yes and input('All the data here is replaced by the export (a copy goes to data/backups/ first). Go on? [y/N] ').lower() != 'y':
            raise CommandError('Nothing changed.')
        try:
            manifest = backup.import_from(file)
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages))
        self.stdout.write(self.style.SUCCESS(f'Imported the data exported on {manifest["made"]}.'))
