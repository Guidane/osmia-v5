"""
Run Osmia as a server:  python serve.py [--host 0.0.0.0] [--port 8000] [--threads 8]

It watches over the server: the server applies database migrations, then serves Osmia (and its static files) with
waitress; when it asks to be started again (after Osmia was updated from its Update page), it is. Ctrl+C stops it.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from osmia.version import RESTART  # noqa: E402  (after BASE_DIR is on the path)


def say(text):
    print(text, flush=True)


def watch():
    """Run the server in a process of its own, and again each time it exits asking for it."""
    env = dict(os.environ, OSMIA_SERVER='1')
    while True:
        try:
            code = subprocess.call([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=env)
        except KeyboardInterrupt:
            say('Osmia stopped.')
            return
        if code != RESTART:
            sys.exit(code)
        say('Osmia is starting again…')


def serve_osmia(args):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'osmia.settings')
    import django
    django.setup()
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    from django.contrib.staticfiles.handlers import StaticFilesHandler

    from osmia.wsgi import application
    app = StaticFilesHandler(application)
    say(f'Osmia is running on http://{args.host}:{args.port}/')
    try:
        from waitress import serve
    except ImportError:
        from wsgiref.simple_server import make_server
        say('waitress is not installed (pip install -r requirements.txt); using the basic Python server.')
        make_server(args.host, args.port, app).serve_forever()
        return
    try:
        serve(app, host=args.host, port=args.port, threads=args.threads, max_request_body_size=200 * 1024 ** 2)
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(description='Run Osmia.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--threads', type=int, default=8)
    args = parser.parse_args()
    if os.environ.get('OSMIA_SERVER') == '1':
        serve_osmia(args)
    else:
        watch()


if __name__ == '__main__':
    main()
