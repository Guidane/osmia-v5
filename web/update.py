"""Updating Osmia from inside it: an administrator uploads the code as a .zip (GitHub: Code → Download ZIP), and Osmia

1. checks it is Osmia's code, and not older than the data here (its migrations must include all those applied);
2. saves the data (an export) and the code there is now to ``data/backups/``;
3. puts the new code in place of the old (``data``, ``.venv``, ``.git`` and other things that aren't code stay);
4. installs its requirements, if they changed, and runs its migrations;
5. starts again (when run by ``serve.py``; else it says to start it again).

When 4 fails, the old code and the data are put back, and it says what went wrong."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection

from osmia.version import RESTART

KEEP = {'data', '.venv', 'venv', '.git', '.idea', '.vscode', '.env', 'example software', '__pycache__'}   # never touched
DJANGO = {'admin', 'auth', 'contenttypes', 'sessions'}   # migrations that come with Django, not with Osmia's code


class Release:
    """What an uploaded .zip holds: its files (under ``root``, GitHub's top folder), version and migrations."""
    def __init__(self, zf):
        names = [n for n in zf.namelist() if not n.endswith('/')]
        tops = {PurePosixPath(n).parts[0] for n in names}
        self.root = f'{tops.pop()}/' if len(tops) == 1 and not any(n.count('/') == 0 for n in names) else ''
        self.files = [n[len(self.root):] for n in names if n.startswith(self.root)]
        for name in self.files:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or ':' in name:
                raise ValidationError(f'The .zip holds a file it shouldn\'t: {name}.')
        if 'manage.py' not in self.files or 'osmia/settings.py' not in self.files:
            raise ValidationError('This is not Osmia\'s code: download it from the GitHub page with Code → Download ZIP.')
        found = re.search(r"VERSION = '([^']+)'", zf.read(self.root + 'osmia/version.py').decode()) \
            if 'osmia/version.py' in self.files else None
        self.version = found.group(1) if found else 'unknown'
        self.migrations = {(PurePosixPath(n).parts[0], PurePosixPath(n).stem) for n in self.files
                           if re.fullmatch(r'[^/]+/migrations/\d{4}_\w+\.py', n)}
        self.tops = {PurePosixPath(n).parts[0] for n in self.files} - KEEP


def open_zip(upload):
    try:
        return zipfile.ZipFile(upload)
    except zipfile.BadZipFile:
        raise ValidationError('That is not a .zip file.')


def check(zf):
    """The release in ``zf``, refused when it isn't Osmia's code or is older than the data here."""
    release = Release(zf)
    with connection.cursor() as cursor:
        cursor.execute('SELECT app, name FROM django_migrations')
        applied = {(app, name) for app, name in cursor.fetchall() if app not in DJANGO}
    missing = sorted(applied - release.migrations)
    if missing:
        raise ValidationError(f'This code is older than the data here (it hasn\'t {missing[0][0]} {missing[0][1]}): '
                              'take the newest code from GitHub.')
    return release


def _code(base):
    """The top-level things of the code there is now (not the data, the environment, …)."""
    return sorted(p for p in base.iterdir() if p.name not in KEEP
                  and (p.suffix in ('.py', '.txt', '.md', '.cfg', '.toml') or p.name.startswith('.git')
                       or (p.is_dir() and ((p / '__init__.py').exists() or (p / 'apps.py').exists()))))


def _replace(base, source, tops):
    """The code under ``base`` becomes what is under ``source`` (``tops``: its top-level things)."""
    for old in _code(base):
        if old.is_dir():
            shutil.rmtree(old)
        else:
            old.unlink()
    for name in tops:
        new = source / name
        if new.is_dir():
            shutil.copytree(new, base / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        else:
            shutil.copy2(new, base / name)


def _run(*command, base):
    """Run a command of the new code (in Osmia's folder, with this Python): (it worked, what it said)."""
    done = subprocess.run([sys.executable, *command], cwd=base, capture_output=True, text=True, timeout=900,
                          env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    return done.returncode == 0, (done.stdout + done.stderr).strip()


def update(upload, base=None):
    """Install the code in ``upload`` (a .zip), as the module's text says. Returns (the release, whether it starts
    again by itself)."""
    from . import backup
    base = Path(base or settings.BASE_DIR)
    with open_zip(upload) as zf:
        release = check(zf)
        stamp = f'{datetime.now():%Y%m%d-%H%M%S}'
        backups = Path(settings.DATA_DIR) / 'backups'
        backups.mkdir(parents=True, exist_ok=True)
        data_backup = backups / f'before-update-{stamp}.zip'
        code_backup = backups / f'code-before-update-{stamp}.zip'
        backup.export_to(data_backup)
        with zipfile.ZipFile(code_backup, 'w', zipfile.ZIP_DEFLATED) as out:
            for top in _code(base):
                for path in [top] if top.is_file() else sorted(top.rglob('*')):
                    if path.is_file() and '__pycache__' not in path.parts:
                        out.write(path, path.relative_to(base).as_posix())
        old_requirements = (base / 'requirements.txt').read_bytes() if (base / 'requirements.txt').exists() else b''
        with tempfile.TemporaryDirectory() as tmp:
            for name in zf.namelist():
                if name.startswith(release.root) and not name.endswith('/'):
                    target = Path(tmp) / name[len(release.root):]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(name))
            _replace(base, Path(tmp), release.tops)
    steps = []
    if (base / 'requirements.txt').exists() and (base / 'requirements.txt').read_bytes() != old_requirements:
        steps.append(('-m', 'pip', 'install', '-r', 'requirements.txt'))
    steps.append(('manage.py', 'migrate', '--noinput'))
    for step in steps:
        ok, said = _run(*step, base=base)
        if not ok:   # back as it was: the old code and the data
            with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(code_backup) as zf:
                zf.extractall(tmp)
                _replace(base, Path(tmp), {p.name for p in Path(tmp).iterdir()})
            backup.import_from(data_backup)
            raise ValidationError(f'The update to {release.version} didn\'t work, so Osmia is as it was. '
                                  f'"{" ".join(step)}" said: {said[-1500:]}')
    return release, restart_soon()


def restart_soon():
    """When ``serve.py`` runs Osmia, it is started again in a moment (with the new code): True. Else False."""
    if os.environ.get('OSMIA_SERVER') != '1':
        return False
    threading.Timer(2, os._exit, [RESTART]).start()   # after the page saying so has gone out
    return True
