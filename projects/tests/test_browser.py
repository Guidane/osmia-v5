"""The project diagram in a real browser: dragging a device moves it in that configuration only, and clicking a
harness picks it in the list below."""
from django.core.management import call_command

from projects import configs
from projects.models import Configuration
from web.tests.browser import BrowserTestCase, expect


class DiagramTests(BrowserTestCase):
    def test_dragging_a_device_and_picking_a_harness(self):
        call_command('demo', stdout=open('nul', 'w'))
        base, two = Configuration.objects.get(name='Base'), Configuration.objects.get(name='Two load boards')
        page = self.go(two.get_absolute_url())
        expect(page.locator('#diagram .device')).to_have_count(3)
        expect(page.locator('#diagram .device.added')).to_have_count(1)        # Load board 2
        controller = next(k for k, r in configs.resolve(two).items() if r['label'] == 'Controller')
        before = configs.resolve(two)[controller]['x']
        with page.expect_response(lambda r: r.request.method == 'POST'):
            self.drag(page.locator(f'#diagram .device[data-key="{controller}"]'), (120, 0))
        self.assertGreater(configs.resolve(two)[controller]['x'], before + 50)
        self.assertEqual(configs.resolve(base)[controller]['x'], before)       # the parent stays where it was
        page.locator('#diagram .pill', has_text='H-0002').click()
        expect(page.locator('tr.placed.picked')).to_contain_text('H-0002')
