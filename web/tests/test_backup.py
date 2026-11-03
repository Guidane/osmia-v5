"""Export and import: everything goes into one file and comes back from it (the database and uploaded files), what was
here is kept in data/backups first, and a file from a newer Osmia, or with files where they don't belong, is refused."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from inventory.models import Part
from web import backup


class BackupTests(TransactionTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.media = root / 'media'
        (self.media / 'images').mkdir(parents=True)
        (self.media / 'images' / 'plug.png').write_bytes(b'a picture')
        self.settings = override_settings(MEDIA_ROOT=self.media, DATA_DIR=root)
        self.settings.enable()
        self.ada = get_user_model().objects.create_superuser('ada', 'ada@example.com', 'pw')

    def tearDown(self):
        self.settings.disable()
        self.tmp.cleanup()

    def test_exported_and_imported_back(self):
        Part.objects.create(number='OURS-1', description='Ours')
        out = io.BytesIO()
        backup.export_to(out)
        Part.objects.all().delete()
        Part.objects.create(number='LATER')
        (self.media / 'images' / 'plug.png').unlink()
        out.seek(0)
        manifest = backup.import_from(out)
        self.assertEqual(list(Part.objects.values_list('number', flat=True)), ['OURS-1'])
        self.assertEqual((self.media / 'images' / 'plug.png').read_bytes(), b'a picture')
        self.assertIn(['inventory', '0001_initial'], manifest['migrations'])
        saved = list((Path(self.tmp.name) / 'backups').glob('before-import-*.zip'))
        self.assertEqual(len(saved), 1)                                           # what was here, kept first
        with zipfile.ZipFile(saved[0]) as zf:
            self.assertIn('db.sqlite3', zf.namelist())

    def remade(self, change):
        out = io.BytesIO()
        backup.export_to(out)
        out.seek(0)
        with zipfile.ZipFile(out) as zf:
            files = {n: zf.read(n) for n in zf.namelist()}
        change(files)
        made = io.BytesIO()
        with zipfile.ZipFile(made, 'w') as zf:
            for name, data in files.items():
                zf.writestr(name, data)
        made.seek(0)
        return made

    def test_a_newer_osmia_s_data_or_a_strange_file_is_refused(self):
        def newer(files):
            manifest = json.loads(files['manifest.json'])
            manifest['migrations'].append(['inventory', '0099_from_the_future'])
            files['manifest.json'] = json.dumps(manifest)
        with self.assertRaisesMessage(ValidationError, 'from a newer Osmia'):
            backup.import_from(self.remade(newer))
        with self.assertRaisesMessage(ValidationError, "holds a file it shouldn't"):
            backup.import_from(self.remade(lambda files: files.update({'../evil.py': b'x'})))
        with self.assertRaisesMessage(ValidationError, 'not an export of Osmia'):
            backup.import_from(self.remade(lambda files: files.pop('manifest.json')))
        self.assertFalse((Path(self.tmp.name) / 'backups').exists())             # refused before anything changed

    def test_the_page(self):
        self.client.force_login(self.ada)
        response = self.client.post(reverse('web:transfer'), {'action': 'export'})
        self.assertEqual(response['Content-Disposition'].split('filename=')[1][:7], '"osmia-')
        data = b''.join(response.streaming_content)
        self.assertIn('manifest.json', zipfile.ZipFile(io.BytesIO(data)).namelist())
        response = self.client.post(reverse('web:transfer'), {'file': io.BytesIO(data), 'sure': '1'})
        self.assertRedirects(response, reverse('accounts:login'), fetch_redirect_response=False)
        self.client.force_login(get_user_model().objects.create_user('bob'))
        self.assertEqual(self.client.get(reverse('web:transfer')).status_code, 404)
