"""Updating Osmia from an uploaded .zip of its code (into a folder made for the test, never over the real code): the new
code takes the place of the old (data, the environment and git stay), requirements are installed when they changed
and the migrations run; when that fails, the old code and the data are put back; code older than the data, or not
Osmia's, is refused."""
import io
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from inventory.models import Part
from web import update


def release(migrations=True, extra=None, requirements='Django>=5.2\n'):
    """A .zip as GitHub gives it: everything in one top folder."""
    files = {'manage.py': 'print("new")', 'osmia/__init__.py': '', 'osmia/settings.py': '# new',
             'osmia/version.py': "VERSION = '9.9.9'\n", 'newapp/__init__.py': '', 'newapp/views.py': '# new app',
             'README.md': 'new', 'requirements.txt': requirements}
    if migrations:
        with connection.cursor() as cursor:
            cursor.execute('SELECT app, name FROM django_migrations')
            for app, name in cursor.fetchall():
                if app not in update.DJANGO:
                    files[f'{app}/migrations/{name}.py'] = ''
    files.update(extra or {})
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as zf:
        zf.writestr('osmia-v5-main/', '')
        for name, text in files.items():
            zf.writestr(f'osmia-v5-main/{name}', text)
    out.seek(0)
    return out


class UpdateTests(TransactionTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.base = root / 'osmia'
        for name, text in {'manage.py': 'print("old")', 'osmia/__init__.py': '', 'osmia/settings.py': '# old',
                           'oldapp/__init__.py': '', 'README.md': 'old', 'requirements.txt': 'Django>=5.2\n',
                           'data/keep.txt': 'our data', '.venv/keep.txt': 'the environment', '.git/HEAD': 'ref'}.items():
            path = self.base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.settings = override_settings(MEDIA_ROOT=root / 'media', DATA_DIR=root / 'data-dir')
        self.settings.enable()

    def tearDown(self):
        self.settings.disable()
        self.tmp.cleanup()

    def test_the_new_code_takes_the_old_one_s_place(self):
        calls = []
        with mock.patch.object(update, '_run', side_effect=lambda *c, base: calls.append(c) or (True, '')):
            done, again = update.update(release(requirements='Django>=5.2\nopenpyxl>=3.1\n'), base=self.base)
        self.assertEqual((done.version, again), ('9.9.9', False))                # not run by serve.py: start it yourself
        self.assertEqual((self.base / 'manage.py').read_text(), 'print("new")')
        self.assertTrue((self.base / 'newapp' / 'views.py').exists())
        self.assertFalse((self.base / 'oldapp').exists())                         # gone with the old code
        self.assertEqual((self.base / 'data' / 'keep.txt').read_text(), 'our data')
        self.assertTrue((self.base / '.venv' / 'keep.txt').exists())
        self.assertTrue((self.base / '.git' / 'HEAD').exists())
        self.assertEqual(calls, [('-m', 'pip', 'install', '-r', 'requirements.txt'), ('manage.py', 'migrate', '--noinput')])
        backups = sorted(p.name.split('-')[0] for p in (Path(self.tmp.name) / 'data-dir' / 'backups').iterdir())
        self.assertEqual(backups, ['before', 'code'])                             # the data and the code from before

    def test_when_it_fails_it_is_as_it_was(self):
        Part.objects.create(number='OURS-1')
        with mock.patch.object(update, '_run', return_value=(False, 'migration 0004 broke')):
            with self.assertRaisesMessage(ValidationError, 'Osmia is as it was'):
                update.update(release(), base=self.base)
        self.assertEqual((self.base / 'manage.py').read_text(), 'print("old")')
        self.assertTrue((self.base / 'oldapp').exists())
        self.assertFalse((self.base / 'newapp').exists())
        self.assertTrue(Part.objects.filter(number='OURS-1').exists())

    def test_older_or_foreign_code_is_refused(self):
        with self.assertRaisesMessage(ValidationError, 'older than the data'):
            update.update(release(migrations=False), base=self.base)
        foreign = io.BytesIO()
        with zipfile.ZipFile(foreign, 'w') as zf:
            zf.writestr('something/readme.txt', 'hello')
        foreign.seek(0)
        with self.assertRaisesMessage(ValidationError, "not Osmia's code"):
            update.update(foreign, base=self.base)
        with self.assertRaisesMessage(ValidationError, "holds a file it shouldn't"):
            update.update(release(extra={'../evil.py': 'x'}), base=self.base)
        self.assertEqual((self.base / 'manage.py').read_text(), 'print("old")')  # refused before anything changed

    def test_the_page(self):
        admin = get_user_model().objects.create_superuser('ada', 'ada@example.com', 'pw')
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse('web:update')), 'this is 5.')
        response = self.client.post(reverse('web:update'), {'file': io.BytesIO(b'not a zip at all')}, follow=True)
        self.assertContains(response, 'That is not a .zip file.')
        self.client.force_login(get_user_model().objects.create_user('bob'))
        self.assertEqual(self.client.get(reverse('web:update')).status_code, 404)
