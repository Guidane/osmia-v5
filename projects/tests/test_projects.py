"""Projects: a configuration tree where each child is its parent with its own changes (added, taken away, swapped,
moved, plugged in differently), changes flowing down, taking a change back, detaching, what is wrong (a harness not
plugged in, plugged into the wrong device, two in one connector) and what building it needs."""
from decimal import Decimal

from django.urls import reverse

from devices.models import Connector, Device
from harnesses.models import HarnessEnd, HarnessItem, Wire
from harnesses.tests.test_harnesses import HarnessBase
from inventory import stock
from orders.models import Order
from projects import configs
from projects.models import Configuration


class ProjectBase(HarnessBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.base = Configuration.objects.create(project=cls.project, name='Base')
        cls.ctrl = configs.place(cls.base, kind='device', device_id=cls.controller.pk, label='Controller')
        cls.load = configs.place(cls.base, kind='device', device_id=cls.board.pk, label='Load board 1', x=300)
        cls.loom = configs.place(cls.base, kind='harness', harness_id=cls.harness.pk, ends=configs.plug(cls.base, cls.harness))
        cls.child = Configuration.objects.create(project=cls.project, name='Two load boards', parent=cls.base)

    def labels(self, config):
        return sorted(r['label'] for r in configs.resolve(config).values() if r['kind'] == 'device')


class TreeTests(ProjectBase):
    def test_a_harness_plugs_itself_in_where_one_device_fits(self):
        ends = configs.resolve(self.base)[self.loom]['ends']
        self.assertEqual(ends, {str(self.p1.pk): self.ctrl, str(self.p2.pk): self.load})
        self.assertEqual(configs.problems(self.base), [])

    def test_a_child_is_its_parent_with_its_changes_and_changes_flow_down(self):
        self.assertEqual(self.labels(self.child), ['Controller', 'Load board 1'])
        second = configs.place(self.child, kind='device', device_id=self.board.pk, label='Load board 2', x=600)
        configs.place(self.child, self.ctrl, x=50, y=80)                        # moved here only
        self.assertEqual(self.labels(self.child), ['Controller', 'Load board 1', 'Load board 2'])
        self.assertEqual(self.labels(self.base), ['Controller', 'Load board 1'])
        configs.place(self.base, self.load, label='Load board A')               # a change to the parent flows down
        self.assertEqual(self.labels(self.child), ['Controller', 'Load board 2', 'Load board A'])
        kinds = sorted(what for _, what, _ in configs.changes(self.child))
        self.assertEqual(kinds, ['added', 'changed'])
        grandchild = Configuration.objects.create(project=self.project, name='Without the second', parent=self.child)
        configs.take_away(grandchild, second)
        self.assertEqual(self.labels(grandchild), ['Controller', 'Load board A'])
        self.assertEqual([what for _, what, _ in configs.changes(grandchild)], ['removed'])

    def test_taking_a_device_away_unplugs_its_harness_and_undo_brings_it_back(self):
        configs.take_away(self.child, self.load)
        self.assertEqual(self.labels(self.child), ['Controller'])
        self.assertIn(f'{self.harness.number} P2 is not plugged in.', [t for _, t in configs.problems(self.child)])
        for placement, _, _ in configs.changes(self.child):
            configs.undo(self.child, placement.pk)
        self.assertEqual(configs.resolve(self.child), configs.resolve(self.base))

    def test_swapping_a_device_and_plugging_wrongly(self):
        other = Device.objects.create(number='LOAD-2', name='Bigger load board')
        Connector.objects.create(device=other, designator='J1')
        configs.place(self.child, self.load, device_id=other.pk)
        self.assertIn(f'{self.harness.number} P2 is for LOAD-1 J1, but Load board 1 is a LOAD-2 Bigger load board.',
                      [t for _, t in configs.problems(self.child)])
        configs.place(self.child, self.loom, ends={str(self.p1.pk): self.ctrl, str(self.p2.pk): self.ctrl})
        self.assertTrue(any('is for LOAD-1 J1' in t for _, t in configs.problems(self.child)))

    def test_detach_and_copy(self):
        configs.place(self.child, kind='device', device_id=self.board.pk, label='Load board 2')
        configs.detach(self.child)
        self.child.refresh_from_db()
        self.assertIsNone(self.child.parent)
        configs.place(self.base, self.load, label='Renamed')                    # no longer flows into it
        self.assertEqual(self.labels(self.child), ['Controller', 'Load board 1', 'Load board 2'])
        copy = configs.copy(self.base, 'Field test')
        self.assertEqual(self.labels(copy), ['Controller', 'Renamed'])


class PageTests(ProjectBase):
    def test_wire_diagrams_live_at_wire_diagrams(self):
        self.assertEqual(self.project.get_absolute_url(), f'/wire-diagrams/{self.project.pk}/')

    def test_the_project_page_and_its_changes(self):
        url = reverse('projects:change', args=[self.project.pk])
        self.client.post(url, {'config': self.child.pk, 'action': 'add_device', 'device': self.board.pk})
        self.assertIn('LOAD-1 2', self.labels(self.child))                      # a name of its own
        response = self.client.post(url, {'config': self.child.pk, 'action': 'move', 'key': self.ctrl, 'x': '120', 'y': '40'})
        self.assertEqual(response.json(), {'ok': True})
        self.assertEqual(configs.resolve(self.child)[self.ctrl]['x'], 120)
        page = self.client.get(self.child.get_absolute_url())
        self.assertContains(page, 'LOAD-1 2 added')
        self.assertContains(page, 'Controller: moved')
        self.assertContains(page, 'diagram-data')
        self.client.post(reverse('projects:configuration', args=[self.project.pk]),
                         {'action': 'new', 'name': 'Rev C', 'parent': self.child.pk})
        self.assertTrue(Configuration.objects.filter(name='Rev C', parent=self.child).exists())
        response = self.client.post(reverse('projects:configuration', args=[self.project.pk]),
                                    {'action': 'delete', 'config': self.base.pk}, follow=True)
        self.assertContains(response, 'has configurations under it')

    def test_what_it_needs_and_ordering_what_is_missing(self):
        Wire.objects.create(harness=self.harness, from_end=self.p1, from_pin='1', to_end=self.p2, to_pin='1', length=Decimal(400), part=self.wire)
        HarnessItem.objects.create(harness=self.harness, part=self.plug, quantity=1)
        stock.add(self.plug, 1, self.shelf, self.ada)
        devices, harnesses, parts = configs.needs(self.base)
        self.assertEqual([(d.number, n) for d, n in devices], [('CTRL-1', 1), ('LOAD-1', 1)])
        needed = {p.number: (q, have) for p, q, have, _ in parts}
        self.assertEqual(needed['DSUB-9-PLUG'], (3, 1))                         # two ends and one extra
        self.assertEqual(needed['WIRE-22-RED'][0], Decimal('0.4'))
        self.client.post(reverse('projects:needs', args=[self.project.pk]) + f'?config={self.base.pk}&count=2')
        line = Order.objects.get().lines.get()
        self.assertEqual((line.part, line.quantity), (self.plug, 5))           # 6 needed, 1 on hand
        response = self.client.get(reverse('projects:needs', args=[self.project.pk]), {'config': self.base.pk, 'export': 1})
        self.assertEqual(response.status_code, 200)

    def test_two_harnesses_in_one_connector(self):
        from harnesses.models import Harness
        other = Harness.objects.create(project=self.project, name='Spare loom')
        HarnessEnd.objects.create(harness=other, designator='P1', connector=self.j1)
        configs.place(self.base, kind='harness', harness_id=other.pk, ends=configs.plug(self.base, other))
        self.assertTrue(any('both plug into Controller J1' in t for _, t in configs.problems(self.base)))


class ConnectTests(ProjectBase):
    def test_a_harness_made_between_two_connectors(self):
        self.j1.pins.filter(number__in=['6', '7']).update(wire_set='CAN', set_type='Twisted')
        response = self.client.post(reverse('projects:change', args=[self.project.pk]), {
            'config': self.child.pk, 'action': 'connect', 'name': 'Controller J1 to board J1',
            'a': self.ctrl, 'a_connector': self.j1.pk, 'b': self.load, 'b_connector': self.board_j1.pk,
            'wire': ['["1", "1"]', '["2", "3"]', '["6", "2"]']}, follow=True)
        harness = self.project.harnesses.get(name='Controller J1 to board J1')
        self.assertContains(response, f'{harness} is made, with 3 wires.')
        p1, p2 = harness.ends.all()
        self.assertEqual((p1.designator, p1.connector, p2.designator, p2.connector), ('P1', self.j1, 'P2', self.board_j1))
        self.assertEqual(sorted((w.from_pin, w.to_pin, w.signal, w.wire_set, w.set_type) for w in harness.wires.all()),
                         [('1', '1', '+24 V', '', 'Straight'), ('2', '3', '0 V', '', 'Straight'), ('6', '2', 'CAN H', 'CAN', 'Twisted')])
        row = next(r for r in configs.resolve(self.child).values() if r['harness_id'] == harness.pk)
        self.assertEqual(row['ends'], {str(p1.pk): self.ctrl, str(p2.pk): self.load})   # placed here, plugged in
        self.assertFalse(any(r['harness_id'] == harness.pk for r in configs.resolve(self.base).values()))

    def test_what_can_t_be_connected(self):
        def connect(**post):
            return self.client.post(reverse('projects:change', args=[self.project.pk]), {
                'config': self.base.pk, 'action': 'connect', 'name': 'x', 'a': self.ctrl, 'a_connector': self.j1.pk, **post}, follow=True)
        self.assertContains(connect(b=self.ctrl, b_connector=self.j1.pk), 'Pick two different connectors.')
        self.assertContains(connect(b=self.ctrl, b_connector=self.board_j1.pk), 'That connector is not in this configuration.')
        self.assertContains(connect(b=self.load, b_connector=self.board_j1.pk, wire='["99", "1"]'), 'There is no pin 99 on that connector.')
        self.assertFalse(self.project.harnesses.filter(name='x').exists())


class HarnessRequestTests(ProjectBase):
    def ask(self, **post):
        return self.client.post(reverse('projects:change', args=[self.project.pk]), {
            'config': self.base.pk, 'action': 'request_harness', 'a': self.ctrl, 'b': self.load, **post}, follow=True)

    def test_asked_made_between_the_two_and_who_asked_hears(self):
        from django.contrib.auth import get_user_model
        from projects.models import HarnessRequest
        from web.models import Notification
        sam = get_user_model().objects.create_user('sam', password='pw')
        bob = get_user_model().objects.create_user('bob', password='pw')
        self.client.force_login(sam)
        self.assertContains(self.ask(request=''), 'Say what is needed.')
        self.assertContains(self.ask(request='Sensor cable, 2 m', b='nope'), 'Pick two devices of this configuration.')
        page = self.ask(request='Sensor cable, 2 m', ask=bob.pk)
        self.assertContains(page, 'Controller ⇄ Load board 1')
        wanted = HarnessRequest.objects.get()
        self.assertTrue(Notification.objects.filter(user=bob, message__contains='harness between Controller and Load board 1').exists())
        self.assertIn({'id': wanted.pk, 'a': self.ctrl, 'b': self.load, 'text': 'Sensor cable, 2 m'},
                      page.context['diagram']['requests'])
        self.client.force_login(self.ada)
        self.assertContains(self.client.get('/'), '1</b> harness asked for', html=False)
        self.client.post(reverse('projects:change', args=[self.project.pk]), {    # drawn between the two: made
            'config': self.base.pk, 'action': 'connect', 'name': 'Sensor cable', 'a': self.load, 'a_connector': self.board_j1.pk,
            'b': self.ctrl, 'b_connector': self.j1.pk})
        wanted.refresh_from_db()
        self.assertEqual((wanted.status, wanted.harness.name), ('done', 'Sensor cable'))
        self.assertTrue(Notification.objects.filter(user=sam, message__contains='is made').exists())
        self.assertNotContains(self.client.get('/'), 'harness asked for')

    def test_done_or_cancelled_by_hand(self):
        from projects.models import HarnessRequest
        self.ask(request='A loom')
        self.ask(request='Another loom')
        first, second = HarnessRequest.objects.order_by('pk')
        change = reverse('projects:change', args=[self.project.pk])
        self.client.post(change, {'config': self.base.pk, 'action': 'request_done', 'request_id': first.pk, 'harness': self.harness.pk})
        self.client.post(change, {'config': self.base.pk, 'action': 'request_cancel', 'request_id': second.pk})
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((first.status, first.harness, second.status), ('done', self.harness, 'cancelled'))
        response = self.client.post(change, {'config': self.base.pk, 'action': 'request_cancel', 'request_id': first.pk}, follow=True)
        self.assertContains(response, 'That request is closed already.')
