from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from web import demo


class Command(BaseCommand):
    help = 'Switch the demo data on (example data alongside what is there), or off (--off: every row it made goes).'

    def add_arguments(self, parser):
        parser.add_argument('--off', action='store_true', help='take the demo data away')

    def handle(self, off=False, **options):
        try:
            if off:
                kept = demo.switch_off()
                self.stdout.write(self.style.SUCCESS('The demo data is off.'))
                if kept:
                    self.stdout.write(f'Kept, because real data uses them: {", ".join(kept)}')
            else:
                user = get_user_model().objects.filter(is_superuser=True).order_by('pk').first()
                demo.switch_on(user)
                self.stdout.write(self.style.SUCCESS('The demo data is on: open Home, the Burn-in rack project, or a device.'))
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages))
