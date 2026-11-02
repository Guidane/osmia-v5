"""Osmia in a real browser: a live server, Playwright (Edge, Chrome, or Playwright's Chromium) and helpers. A
JavaScript error on any page fails the test.

Slow, so tagged: ``manage.py test --tag browser`` runs only these, ``--exclude-tag browser`` everything else. Without
Playwright (``pip install -r requirements-dev.txt``) or a browser they're skipped.
"""
import os
from unittest import SkipTest

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import tag

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:   # the fast tests run without it
    expect = sync_playwright = None

TIMEOUT = 10_000   # ms: how long a page may take to show something


@tag('browser')
class BrowserTestCase(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise SkipTest('Playwright is not installed: pip install -r requirements-dev.txt')
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'   # Playwright's sync API runs an event loop in this thread
        super().setUpClass()
        cls._playwright = sync_playwright().start()
        cls.browser = None
        for options in ({'channel': 'msedge'}, {'channel': 'chrome'}, {}):
            try:
                cls.browser = cls._playwright.chromium.launch(**options)
                break
            except Exception:
                continue
        if cls.browser is None:
            cls._playwright.stop()
            super().tearDownClass()
            raise SkipTest('No browser to test with: install Edge or Chrome, or run "playwright install chromium".')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'pw', first_name='Ada')
        self.context = None
        self.errors = []
        self.log_in(self.admin)

    def tearDown(self):
        if self.context is not None:
            self.context.close()
        self.assertEqual(self.errors, [], 'The pages had JavaScript errors')

    def log_in(self, user):
        """A fresh browser window logged in as ``user``."""
        if self.context is not None:
            self.context.close()
        self.client.force_login(user)
        self.context = self.browser.new_context(viewport={'width': 1400, 'height': 900})
        self.context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                                   'url': self.live_server_url}])
        self.page = self.context.new_page()
        self.page.set_default_timeout(TIMEOUT)
        self.page.on('pageerror', lambda e: self.errors.append(f'{self.page.url}: {e}'))
        self.page.on('dialog', lambda d: d.accept())
        return self.page

    def go(self, path):
        self.page.goto(self.live_server_url + path)
        self.page.wait_for_load_state('networkidle')
        return self.page

    def see(self, text):
        expect(self.page.locator('body')).to_contain_text(text)

    def drag(self, source, target):
        """Drag ``source`` (a locator) onto ``target`` (a locator, or an (x, y) offset in pixels)."""
        a = source.bounding_box()
        mouse = self.page.mouse
        mouse.move(a['x'] + a['width'] / 2, a['y'] + a['height'] / 2)
        mouse.down()
        if isinstance(target, tuple):
            mouse.move(a['x'] + a['width'] / 2 + target[0], a['y'] + a['height'] / 2 + target[1], steps=8)
        else:
            b = target.bounding_box()
            mouse.move(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2, steps=8)
        mouse.up()
