"""All of Osmia's data in one .zip file, to move it to another instance (or keep it): a copy of the database, every
uploaded file, and a manifest saying which version of Osmia (its migrations) the data is at.

Importing replaces all the data of this instance with the file's: what is here first goes to ``data/backups/``; then the
migrations run, so data from an older Osmia is brought up to date. Data from a newer Osmia is refused: update this one
first. Administrators do it on the Export / import page, or ``manage.py export_data`` and ``manage.py import_data``."""
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

FORMAT = 1   # of the manifest


def _migrations_known():
    """{(app, migration name)} this Osmia has."""
    return set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations)


def _migrations_applied():
    with connection.cursor() as cursor:
        cursor.execute('SELECT app, name FROM django_migrations')
        return sorted(cursor.fetchall())


def export_to(target):
    """Write the export (a .zip) to ``target``, a path or a file opened for writing in binary."""
    connection.ensure_connection()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'db.sqlite3'
        snapshot = sqlite3.connect(copy)
        with snapshot:
            connection.connection.backup(snapshot)   # a consistent copy, while others may be writing
        snapshot.close()
        manifest = {'osmia': 'export', 'format': FORMAT, 'made': datetime.now().isoformat(timespec='seconds'),
                    'migrations': _migrations_applied()}
        media = Path(settings.MEDIA_ROOT)
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('manifest.json', json.dumps(manifest, indent=1))
            zf.write(copy, 'db.sqlite3')
            if media.is_dir():
                for path in sorted(media.rglob('*')):
                    if path.is_file():
                        zf.write(path, 'media/' + path.relative_to(media).as_posix())


def _check(zf):
    """The manifest of an export, refused when it isn't one, or holds data of a newer Osmia, or unsafe file names."""
    names = zf.namelist()
    if 'manifest.json' not in names or 'db.sqlite3' not in names:
        raise ValidationError('This is not an export of Osmia.')
    manifest = json.loads(zf.read('manifest.json'))
    if manifest.get('osmia') != 'export' or manifest.get('format') != FORMAT:
        raise ValidationError('This is not an export of Osmia (or of a version this one can\'t read).')
    unknown = sorted({tuple(m) for m in manifest.get('migrations', [])} - _migrations_known())
    if unknown:
        raise ValidationError(f'This data is from a newer Osmia (it has {unknown[0][0]} {unknown[0][1]}): update Osmia here first.')
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or (name not in ('manifest.json', 'db.sqlite3') and path.parts[0] != 'media'):
            raise ValidationError(f'The export holds a file it shouldn\'t: {name}.')
    return manifest


def import_from(source):
    """Replace all the data here with the export ``source`` (a path or a file opened in binary). What was here is
    exported to ``data/backups/`` first. Returns the manifest of what came in."""
    from .update import open_zip
    with open_zip(source) as zf:
        manifest = _check(zf)
        backups = Path(settings.DATA_DIR) / 'backups'
        backups.mkdir(parents=True, exist_ok=True)
        export_to(backups / f'before-import-{datetime.now():%Y%m%d-%H%M%S}.zip')
        with tempfile.TemporaryDirectory() as tmp:
            zf.extractall(tmp)
            incoming = sqlite3.connect(Path(tmp) / 'db.sqlite3')
            connection.ensure_connection()
            with incoming:
                incoming.backup(connection.connection)   # the database here becomes the export's
            incoming.close()
            media = Path(settings.MEDIA_ROOT)
            if media.exists():
                shutil.rmtree(media)
            if (Path(tmp) / 'media').is_dir():
                shutil.copytree(Path(tmp) / 'media', media)
            else:
                media.mkdir(parents=True)
    connection.close()
    call_command('migrate', interactive=False, verbosity=0)   # an older export is brought up to date
    return manifest
