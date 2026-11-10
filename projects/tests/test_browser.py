"""The project diagram in a real browser: dragging a device moves it in that configuration only (its lines going
with it while it moves), clicking a harness picks it in the list below, a connector's square shows its pinout, and the
zoom."""
import re

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
        start = free.nth(0)
        other = page.locator(f'#diagram .sq:not(.on):not([data-device="{start.get_attribute("data-device")}"])').first
        self.drag(start, other)                                                 # to a connector of another device
        expect(page.locator('#connect')).to_be_visible()
        expect(page.locator('#connect [name=name]')).not_to_have_value('')
        page.click('#connect button.primary')
        expect(page.locator('#diagram .pill')).to_have_count(before + 1)
        self.assertEqual(base.project.harnesses.count(), 4)

    def test_a_connector_slides_along_its_box_and_a_line_is_pinned_by_its_handle(self):
        from devices.models import Connector
        call_command('demo', stdout=open('nul', 'w'))
        base = Configuration.objects.get(name='Base')
        page = self.go(base.get_absolute_url())
        free = page.locator('#diagram .sq:not(.on)').first
        connector = Connector.objects.get(pk=free.get_attribute('data-connector'))
        box = page.locator(f'#diagram .device[data-key="{free.get_attribute("data-device")}"] .box').bounding_box()
        at = free.bounding_box()
        page.mouse.move(at['x'] + at['width'] / 2, at['y'] + at['height'] / 2)
        page.mouse.down()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 4, steps=8)          # along the outline, to the top
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.mouse.up()
        connector.refresh_from_db()
        self.assertEqual(connector.side, 'top')
        dot = page.locator('#diagram .handle').first
        expect(dot).not_to_have_class('handle pinned')
        with page.expect_response(lambda r: r.request.method == 'POST'):
            dot.click()                                                           # pinned where it is
        expect(page.locator('#diagram .handle.pinned')).to_have_count(1)
        row = next(r for r in configs.resolve(base).values() if r['kind'] == 'harness')
        self.assertEqual(len(row['handles']), 1)
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.locator('#diagram .handle.pinned').click()                      # let go
        expect(page.locator('#diagram .handle.pinned')).to_have_count(0)
        self.assertEqual(next(r for r in configs.resolve(base).values() if r['kind'] == 'harness')['handles'], {})
        handle = page.locator('#diagram .handle').first.bounding_box()
        page.mouse.move(handle['x'] + 5, handle['y'] + 5)
        page.mouse.down()
        page.mouse.move(handle['x'] + 5, handle['y'] + 120, steps=6)              # dragged: pinned there
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.mouse.up()
        expect(page.locator('#diagram .handle.pinned')).to_have_count(1)

    def test_pin_sets_from_a_list(self):
        from devices.models import Connector
        call_command('demo', stdout=open('nul', 'w'))
        bus = Connector.objects.get(device__number='CTRL-100', designator='J1')
        page = self.go(f'/devices/{bus.device_id}/connectors/{bus.pk}/pins/')
        rows = page.locator('#pins tr')
        enable = rows.nth(3)                                                         # pin 3, Enable: no set
        enable.locator('[data-set]').select_option('+')
        expect(enable.locator('[data-set]')).to_have_value('1')                      # the next free number
        expect(rows.nth(1).locator('[data-set] option', has_text='1')).to_have_count(1)   # in every list
        rows.nth(1).locator('[data-type]').select_option('Shielded')                # +24 V, set PWR
        expect(rows.nth(2).locator('[data-type]')).to_have_value('Shielded')         # 0 V too

    def test_a_harness_pinout_drawn_and_a_set_lit_up(self):
        from harnesses.models import Harness
        call_command('demo', stdout=open('nul', 'w'))
        page = self.go(Harness.objects.get(name='Controller to load board').get_absolute_url())
        expect(page.locator('#pinout-drawing .pd-pin')).to_have_count(18)               # two D-sub 9 faces, every position
        page.locator('#set-chips button', has_text='CAN').click()
        expect(page.locator('#pinout-drawing .pd-contact.lit')).to_have_count(6)        # CAN H, CAN L and the shield, both ends
        expect(page.locator('#pinout-drawing .pd-pin.lit')).to_have_count(6)
        page.locator('#set-chips button', has_text='CAN').click()                        # again: none
        expect(page.locator('#pinout-drawing .lit')).to_have_count(0)
        page.locator('#pinout-drawing .pd-area[data-set="PWR"]').click()                 # where the set's wires run
        expect(page.locator('#pinout-drawing .pd-contact.lit')).to_have_count(4)
        page.locator('#pinout-drawing .pd-area[data-set^="wire:"]').click()             # Enable, in no set: on its own
        expect(page.locator('#pinout-drawing .pd-contact.lit')).to_have_count(2)

    def test_a_harness_pinout_drawn_in_edit_mode(self):
        from harnesses.models import Harness
        call_command('demo', stdout=open('nul', 'w'))
        harness = Harness.objects.get(name='Controller to load board')
        page = self.go(harness.get_absolute_url())
        before = harness.wires.count()
        page.click('#set-chips [data-mode=edit]')
        page.locator('#pinout-drawing .pd-pin[data-pin="4"]').first.click()              # P1:4 …
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.locator('#pinout-drawing .pd-pin[data-pin="4"]').nth(1).click()          # … to P2:4: a new row
        expect(page.locator('#pinout-drawing .pd-contact')).to_have_count(2 * (before + 1))
        made = harness.wires.order_by('-pk').first()
        self.assertEqual((made.from_pin, made.to_pin), ('4', '4'))
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.locator(f'#pinout-drawing select[data-wire="{made.pk}"]').select_option('new:Straight')   # a new set
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.locator(f'#pinout-drawing select[data-wire-type="{made.pk}"]').select_option('Twisted')   # then its type
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.locator(f'#pinout-drawing input[data-wire-gauge="{made.pk}"]').fill('22')
            page.locator(f'#pinout-drawing input[data-wire-gauge="{made.pk}"]').press('Enter')       # its gauge
        expect(page.locator(f'#pinout-drawing input[data-wire-gauge="{made.pk}"]')).to_have_value('22 AWG')
        page.click(f'#pinout-drawing [data-wire-signal="{made.pk}"]')                     # its purpose: from the tree
        page.click('.purpose-finder [data-purpose-tree] button:has-text("Power")')
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.click('.purpose-finder [data-purpose="+5V"]')
        expect(page.locator(f'#pinout-drawing [data-wire-signal="{made.pk}"]')).to_have_text('+5V')
        made.refresh_from_db()
        self.assertEqual((made.set_type, made.gauge, made.signal), ('Twisted', '22 AWG', '+5V'))
        page.locator('#pinout-drawing .pd-contact').filter(has=page.locator('text.pd-num', has_text=re.compile('^4$'))).first.click()           # P1:4 again, now to P2:6: a splice
        with page.expect_response(lambda r: r.request.method == 'POST'):
            page.locator('#pinout-drawing .pd-pin[data-pin="6"]').nth(1).click()
        self.assertEqual(harness.wires.filter(from_pin='4').count(), 2)
        page.click('#set-chips [data-mode=view]')                                         # back: the page again, its table too
        expect(page.locator('table.list', has_text='Signal')).to_contain_text(made.wire_set)
