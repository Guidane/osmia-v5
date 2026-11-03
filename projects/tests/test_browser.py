"""The project diagram in a real browser: dragging a device moves it in that configuration only (its lines going
with it while it moves), clicking a harness picks it in the list below, a connector's square shows its pinout, and the
zoom."""
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
        page.locator('#diagram .pill', has_text='Load board link').click()   # (its number depends on the tests before)
        expect(page.locator('tr.placed.picked')).to_contain_text('Load board link')

    def test_lines_follow_a_device_while_it_moves_and_the_zoom(self):
        call_command('demo', stdout=open('nul', 'w'))
        page = self.go(Configuration.objects.get(name='Base').get_absolute_url())
        wires = lambda: page.eval_on_selector_all('#diagram .wire', 'ws => ws.map(w => w.getAttribute("d")).join("|")')
        before = wires()
        box = page.locator('#diagram .device').first.bounding_box()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 20)
        page.mouse.down()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 140, steps=6)
        self.assertNotEqual(wires(), before)                                    # before letting go
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.mouse.up()
        shown = lambda: float(page.get_attribute('#diagram', 'viewBox').split()[2])
        wide = shown()
        page.click('[data-zoom="in"]')
        self.assertLess(shown(), wide)
        page.click('[data-zoom="fit"]')
        self.assertAlmostEqual(shown(), wide, delta=1)

    def test_a_connector_square_shows_its_pinout(self):
        call_command('demo', stdout=open('nul', 'w'))
        page = self.go(Configuration.objects.get(name='Base').get_absolute_url())
        expect(page.locator('#diagram .sq.on').first).to_be_visible()          # where harnesses plug in
        page.locator('#diagram .sq.on').first.click()
        expect(page.locator('#pinout')).to_be_visible()
        expect(page.locator('#pinout tbody tr').first).to_be_visible()
        page.click('#pinout [data-close]')
        expect(page.locator('#pinout')).to_be_hidden()

    def test_dragging_from_square_to_square_makes_a_harness(self):
        call_command('demo', stdout=open('nul', 'w'))
        base = Configuration.objects.get(name='Base')
        page = self.go(base.get_absolute_url())
        before = page.locator('#diagram .pill').count()
        free = page.locator('#diagram .sq:not(.on)')
        self.drag(free.nth(0), free.nth(1))
        expect(page.locator('#connect')).to_be_visible()
        expect(page.locator('#connect [name=name]')).not_to_have_value('')
        page.click('#connect button.primary')
        expect(page.locator('#diagram .pill')).to_have_count(before + 1)
        self.assertEqual(base.project.harnesses.count(), 3)
