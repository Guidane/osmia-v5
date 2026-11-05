"""Harnesses: ends plugged into device connectors, the pinout edited as a table (signals from the devices' pins),
what is wrong with it, its parts list, versions, and building one: a serial number, a checklist, parts out of stock."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from devices.models import Connector, Device, Pin
from devices.tests.test_devices import DeviceBase
from harnesses import views
from assets.models import Asset
from harnesses.models import Harness, HarnessEnd, Wire
from inventory import stock
from projects.models import Project
from web import versions


class HarnessBase(DeviceBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.board = Device.objects.create(number='LOAD-1', name='Load board')
        cls.board_j1 = Connector.objects.create(device=cls.board, designator='J1', name='Bus in')
        for number, signal in (('1', '+24 V'), ('3', '0 V'), ('2', 'CAN H'), ('7', 'CAN L')):
            Pin.objects.create(connector=cls.board_j1, number=number, signal=signal)
        cls.project = Project.objects.create(name='Burn-in rack')
        cls.harness = Harness.objects.create(project=cls.project, name='Bus loom')
        cls.p1 = HarnessEnd.objects.create(harness=cls.harness, designator='P1', part=cls.plug, connector=cls.j1)
        cls.p2 = HarnessEnd.objects.create(harness=cls.harness, designator='P2', part=cls.plug, connector=cls.board_j1, position=1)

    def connect(self, a, b, signal='', **more):
        return Wire.objects.create(harness=self.harness, from_end=self.p1, from_pin=a, to_end=self.p2, to_pin=b, signal=signal, **more)


class PinoutTests(HarnessBase):
    def test_the_pinout_as_a_table_and_what_is_wrong(self):
        p1, p2 = self.p1.pk, self.p2.pk
        self.j1.pins.filter(number='6').update(wire_set='CAN', set_type='Twisted')
        response = self.client.post(reverse('harnesses:pinout', args=[self.harness.pk]), {
            'r0_seen': 1, 'r0_from_end': p1, 'r0_from_pin': '1', 'r0_to_end': p2, 'r0_to_pin': '1', 'r0_length': '450',
            'r0_part': 'wire-22-red', 'r0_colour': 'red',
            'r1_seen': 1, 'r1_from_end': p1, 'r1_from_pin': '6', 'r1_to_end': p2, 'r1_to_pin': '7',           # crossed over
            'r2_seen': 1, 'r2_from_end': p1, 'r2_from_pin': '9', 'r2_to_end': p2, 'r2_to_pin': '3', 'r2_signal': 'GND',
            'r3_seen': 1})
        self.assertRedirects(response, reverse('harnesses:harness', args=[self.harness.pk]))
        wires = {w.from_pin: w for w in self.harness.wires.all()}
        self.assertEqual(wires['1'].signal, '+24 V')                           # taken from the device's pin
        self.assertEqual((wires['6'].wire_set, wires['6'].set_type), ('CAN', 'Twisted'))   # its set too
        self.assertEqual((wires['1'].wire_set, wires['1'].set_type), ('', 'Straight'))
        texts = [t for _, t in self.harness.problems()]
        self.assertIn('P1:6 → P2:7: the wire carries "CAN H", LOAD-1 J1:7 is "CAN L".', texts)
        self.assertIn('CTRL-1 J1 has no pin 9 (P1:9 → P2:3).', texts)
        self.assertIn((self.wire, Decimal('0.45')), self.harness.parts_list())   # metres of wire
        self.assertIn((self.plug, Decimal(2)), self.harness.parts_list())                 # its two ends
        response = self.client.post(reverse('harnesses:pinout', args=[self.harness.pk]), {
            'r0_seen': 1, 'r0_from_end': p1, 'r0_from_pin': '2', 'r0_to_end': p2, 'r0_to_pin': '3', 'r0_part': 'NOPE'}, follow=True)
        self.assertContains(response, 'Row 1: there is no part or family &quot;NOPE&quot;.')
        self.assertEqual(self.harness.wires.count(), 3)                         # nothing of it was kept

    def test_the_pinout_drawn_in_each_connector_s_layout(self):
        from inventory.models import Family
        self.connect('6', '2', wire_set='CAN', set_type='Twisted')
        page = self.client.get(reverse('harnesses:harness', args=[self.harness.pk]))
        p1, p2 = page.context['drawing']['ends']
        self.assertEqual((p1['layout'], p1['positions']), ('row', 0))                     # nothing known: a single row
        self.assertEqual([n for n, _ in p1['pins']], ['1', '2', '6', '7'])                  # the device connector's pins
        dsub = Family.objects.create(name='D-sub 9', pin_layout='staggered', pin_positions=9)
        self.plug.family = dsub
        self.plug.save()
        p1, p2 = self.client.get(reverse('harnesses:harness', args=[self.harness.pk])).context['drawing']['ends']
        self.assertEqual((p1['layout'], p1['positions']), ('staggered', 9))                 # its part's family
        self.board_j1.part = None
        self.board_j1.save()
        self.p2.used = None
        self.p2.save()
        self.assertEqual(self.client.get(reverse('harnesses:harness', args=[self.harness.pk])).context['drawing']['ends'][1]['layout'], 'row')
        self.assertIn({'id': Wire.objects.get().pk, 'from': self.p1.pk, 'from_pin': '6', 'to': self.p2.pk, 'to_pin': '2', 'signal': '', 'set': 'CAN', 'type': 'Twisted',
                       'colour': ''}, page.context['drawing']['wires'])

    def test_the_pinout_edited_in_its_drawing(self):
        url = reverse('harnesses:pinout_draw', args=[self.harness.pk])
        drawing = self.client.post(url, {'action': 'add', 'from_end': self.p1.pk, 'from_pin': '6', 'to_end': self.p2.pk, 'to_pin': '2'}).json()
        wire = Wire.objects.get()
        self.assertEqual((wire.from_pin, wire.to_pin, wire.signal), ('6', '2', 'CAN H'))   # the device pin's signal
        self.assertEqual(drawing['wires'][0]['id'], wire.pk)
        self.client.post(url, {'action': 'set', 'wire': wire.pk, 'set': 'new:Shielded twisted'})
        wire.refresh_from_db()
        self.assertEqual((wire.wire_set, wire.set_type), ('1', 'Shielded twisted'))      # the next free number
        other = self.connect('7', '7')
        self.client.post(url, {'action': 'set', 'wire': other.pk, 'set': '1'})
        other.refresh_from_db()
        self.assertEqual((other.wire_set, other.set_type), ('1', 'Shielded twisted'))    # the set's type
        drain = self.connect('9', '8')
        self.client.post(url, {'action': 'set', 'wire': drain.pk, 'set': 'shield:1'})
        drain.refresh_from_db()
        self.assertEqual((drain.wire_set, drain.set_type), ('1', 'Shield'))
        self.client.post(url, {'action': 'colour', 'wire': drain.pk, 'colour': 'grey'})
        self.assertEqual(Wire.objects.get(pk=drain.pk).colour, 'grey')
        self.client.post(url, {'action': 'delete', 'wire': drain.pk})
        self.assertFalse(Wire.objects.filter(pk=drain.pk).exists())
        self.assertEqual(self.client.post(url, {'action': 'add', 'from_end': self.p1.pk}).status_code, 400)

    def test_one_pin_two_wires(self):
        self.connect('1', '1')
        self.connect('1', '3')
        self.assertIn('P1:1 has 2 wires.', [t for _, t in self.harness.problems()])


class BuildTests(HarnessBase):
    def test_built_with_a_checklist_and_its_parts_from_stock(self):
        self.connect('1', '1', length=Decimal(500), part=self.wire)
        self.connect('2', '3')
        v1 = versions.save(self.harness, self.ada)
        stock.add(self.plug, 5, self.shelf, self.ada)
        stock.add(self.wire, 10, self.shelf, self.ada)
        response = self.client.post(reverse('harnesses:unit_add', args=[self.harness.pk]),
                                    {'serial': 'H-0001-001', 'version': v1.pk, 'take_from': self.shelf.pk})
        unit = Asset.objects.get()
        self.assertRedirects(response, unit.get_absolute_url())
        self.assertEqual((unit.kind, unit.harness, unit.version, unit.status), ('harness', self.harness, 1, 'building'))
        self.assertEqual(self.plug.on_hand, 3)                                  # two connectors went into it
        self.assertEqual(self.wire.on_hand, Decimal('9.5'))
        checks = list(unit.checks.all())
        self.assertEqual([c.wire for c in checks], ['P1:1 → P2:1', 'P1:2 → P2:3'])
        response = self.client.post(reverse('assets:checklist', args=[unit.pk]), {f'verified_{checks[0].pk}': 'on'}, follow=True)
        self.assertContains(response, 'place it before verifying it')
        self.client.post(reverse('assets:checklist', args=[unit.pk]), {f'placed_{c.pk}': 'on' for c in checks} | {f'verified_{c.pk}': 'on' for c in checks})
        self.assertEqual(Asset.objects.get().status, 'available')

    def test_not_without_a_pinout_or_enough_stock(self):
        with self.assertRaisesMessage(ValidationError, 'has no pinout yet'):
            views.build(self.harness, 'X-1', None, self.ada)
        self.connect('1', '1')
        with self.assertRaisesMessage(ValidationError, 'There are only 0 pcs of DSUB-9-PLUG'):
            views.build(self.harness, 'X-1', None, self.ada, take_from=self.shelf)
        self.assertFalse(Asset.objects.exists())

    def test_versions_restore_the_pinout(self):
        self.connect('1', '1', signal='+24 V')
        versions.save(self.harness, self.ada)
        self.harness.wires.all().delete()
        self.harness.ends.filter(designator='P2').update(designator='X2')
        versions.restore(self.harness, self.harness.versions.get())
        self.assertEqual([str(w) for w in self.harness.wires.all()], ['P1:1 → P2:1'])
        self.assertFalse(versions.changed(self.harness))
        page = self.client.get(reverse('harnesses:harness', args=[self.harness.pk]), {'export': 1})
        self.assertEqual(page['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
