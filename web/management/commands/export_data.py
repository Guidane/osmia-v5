from datetime import datetime

from django.core.management.base import BaseCommand

from web import backup


class Command(BaseCommand):
    help = 'Export all of Osmia\'s data (the database and every uploaded file) to one .zip file.'

    def add_arguments(self, parser):
        parser.add_argument('file', nargs='?', help='where to write it (default: osmia-<date>.zip here)')

    def handle(self, file=None, **options):
        file = file or f'osmia-{datetime.now():%Y-%m-%d-%H%M}.zip'
        backup.export_to(file)
        self.stdout.write(self.style.SUCCESS(f'Exported to {file}.'))
