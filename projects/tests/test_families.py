"""Families of parts that can take each other's place: their pages; a harness end (or wire, item, device connector)
naming the family; its stock counted together, building taking the most stocked part first, ordering the preferred
one; versions keeping the family."""
from decimal import Decimal

from django.urls import reverse

from harnesses import views
from inventory import stock
from inventory.models import Branch, Family, Part
from orders.models import Order
from projects import configs
from projects.tests.test_projects import ProjectBase
from web import versions


class FamilyTests(ProjectBase):
    def setUp(self):
        super().setUp()
        self.alt = Part.objects.create(number='DSUB-9-ALT', description='D-sub 9 plug, other make', vendor=self.acme)
        self.family = Family.objects.create(name='D-sub 9 plug')
        Part.objects.filter(pk__in=[self.plug.pk, self.alt.pk]).update(family=self.family)

    def test_its_pages(self):
        self.client.post(reverse('inventory:families'), {'name': 'M12 socket'})
        socket = Family.objects.get(name='M12 socket')
        self.client.post(reverse('inventory:families') + f'?edit={socket.pk}', {'name': 'M12 socket, 5 pin'})   # renamed
        self.assertEqual(Family.objects.get(pk=socket.pk).name, 'M12 socket, 5 pin')
        self.assertContains(self.client.post(reverse('inventory:families'), {'name': 'dsub-9-plug'}), 'That is a part number')
        stock.add(self.plug, 2, self.shelf, self.ada)
        stock.add(self.alt, 3, self.shelf, self.ada)
        page = self.client.get(self.family.get_absolute_url())
        self.assertContains(page, 'DSUB-9-ALT')
        self.assertContains(page, '<b>5</b> pcs on hand, together', html=True)
        page = self.client.get(reverse('inventory:part', args=[self.alt.pk]))
        self.assertContains(page, f'<dt>Family</dt><dd><a href="{self.family.get_absolute_url()}">D-sub 9 plug</a></dd>', html=True)
        self.assertNotContains(page, 'DSUB-9-PLUG')                             # just the family, not its other parts

    def test_a_harness_of_the_family_takes_any_and_orders_the_one_last_ordered(self):
        self.assertEqual(self.family.chosen, self.alt)                         # never ordered: the first (with a vendor)
        order = Order.objects.create(vendor=self.acme)
        order.lines.create(part=self.plug, quantity=1)
        self.assertEqual(self.family.chosen, self.plug)                        # the one last ordered
        order.delete()
        for end in (self.p1, self.p2):
            end.used = self.family
            end.save()
        self.connect('1', '1')
        self.assertEqual(self.harness.parts_list(), [(self.family, Decimal(2))])
        stock.add(self.plug, 1, self.shelf, self.ada)
        stock.add(self.alt, 3, self.shelf, self.ada)
        views.build(self.harness, 'H-1', None, self.ada, take_from=self.shelf)
        self.assertEqual((self.plug.on_hand, self.alt.on_hand), (1, 1))          # the most stocked first
        _, _, parts = configs.needs(self.base)
        self.assertIn((self.family, Decimal(2), Decimal(2), Decimal(0)), parts)   # their stock together
        self.client.post(reverse('projects:needs', args=[self.project.pk]) + f'?config={self.base.pk}&count=3')
        line = Order.objects.get().lines.get()
        self.assertEqual((line.part, line.quantity), (self.alt, 4))              # 6 needed, 2 on hand

    def test_named_in_the_editors_and_kept_in_versions(self):
        self.client.post(reverse('harnesses:items', args=[self.harness.pk]), {'r0_seen': 1, 'r0_part': 'd-sub 9 plug', 'r0_quantity': '2'})
        line = self.harness.items.get()
        self.assertEqual((line.part, line.family), (None, self.family))
        self.assertContains(self.client.get(reverse('harnesses:harness', args=[self.harness.pk])), 'D-sub 9 plug')
        versions.save(self.harness, self.ada)
        self.harness.items.all().delete()
        versions.restore(self.harness, self.harness.versions.get())
        self.assertEqual(self.harness.items.get().family, self.family)
        page = self.client.get(reverse('devices:connector_edit', args=[self.controller.pk, self.j1.pk]))
        self.assertContains(page, 'value="DSUB-9-PLUG"')                         # its part, in the box
        self.assertContains(page, '<option value="D-sub 9 plug">family: 2 parts</option>', html=True)
        self.client.post(reverse('devices:connector_edit', args=[self.controller.pk, self.j1.pk]),
                         {'designator': 'J1', 'name': 'Bus', 'used': 'd-sub 9 plug'})
        self.j1.refresh_from_db()
        self.assertEqual((self.j1.part, self.j1.family), (None, self.family))
        page = self.client.post(reverse('devices:connector_edit', args=[self.controller.pk, self.j1.pk]), {'designator': 'J1', 'used': 'NOPE'})
        self.assertContains(page, 'There is no part or family &quot;NOPE&quot;.')
        self.client.post(reverse('devices:edit', args=[self.board.pk]), {'number': 'LOAD-1', 'name': 'Load board', 'origin': 'external',
                                                                          'colour': '#3b7dd8', 'used': 'D-sub 9 plug'})
        self.board.refresh_from_db()
        self.assertEqual(self.board.used, self.family)                          # a device bought as any part of the family
        _, _, parts = configs.needs(self.base)
        self.assertIn(self.family, [p for p, _, _, _ in parts])

    def test_a_harness_made_between_connectors_gets_its_parts(self):
        self.client.post(reverse('projects:change', args=[self.project.pk]), {
            'config': self.base.pk, 'action': 'connect', 'name': 'Made', 'a': self.ctrl, 'a_connector': self.j1.pk,
            'b': self.load, 'b_connector': self.board_j1.pk, 'a_part': 'D-sub 9 plug', 'b_part': 'dsub-9-alt'})
        p1, p2 = self.project.harnesses.get(name='Made').ends.all()
        self.assertEqual((p1.used, p2.used), (self.family, self.alt))
        response = self.client.post(reverse('projects:change', args=[self.project.pk]), {
            'config': self.base.pk, 'action': 'connect', 'name': 'Wrong', 'a': self.ctrl, 'a_connector': self.j1.pk,
            'b': self.load, 'b_connector': self.board_j1.pk, 'a_part': 'NOPE'}, follow=True)
        self.assertContains(response, 'There is no part or family &quot;NOPE&quot;.')
        self.assertFalse(self.project.harnesses.filter(name='Wrong').exists())

    def test_branches_of_a_family(self):
        page = self.family.get_absolute_url()
        self.client.post(page, {'name': 'pin'})
        self.client.post(page, {'name': 'sockets'})
        self.assertContains(self.client.post(page, {'name': 'PIN'}), 'has a gender PIN already')
        sockets = Branch.objects.get(name='sockets')
        self.client.post(page + f'?branch={sockets.pk}', {'name': 'socket'})               # renamed
        pin, socket = Branch.objects.get(name='pin'), Branch.objects.get(name='socket')
        self.client.post(reverse('inventory:part_edit', args=[self.alt.pk]), {
            'number': 'DSUB-9-ALT', 'unit': 'pcs', 'kin': f'b{socket.pk}', 'minimum': 0, 'reorder_quantity': 0, 'active': 'on'})
        self.alt.refresh_from_db()
        self.assertEqual((self.alt.family, self.alt.branch), (self.family, socket))
        self.assertContains(self.client.get(reverse('inventory:part', args=[self.alt.pk])), 'D-sub 9 plug / socket')
        Part.objects.filter(pk=self.plug.pk).update(branch=pin)
        self.p1.used = self.p2.used = None
        for end, branch in ((self.p1, pin), (self.p2, pin)):
            end.used = branch
            end.save()
        self.assertEqual(self.harness.parts_list(), [(pin, Decimal(2))])
        stock.add(self.alt, 9, self.shelf, self.ada)                                   # a socket: not for the pins
        self.assertEqual(pin.on_hand, 0)
        _, _, parts = configs.needs(self.base)
        self.assertIn((pin, Decimal(2), Decimal(0), Decimal(0)), parts)
        self.client.post(reverse('projects:needs', args=[self.project.pk]) + f'?config={self.base.pk}')
        self.assertEqual(Order.objects.get().lines.get().part, self.plug)              # one of the pins
        self.client.post(reverse('devices:connector_edit', args=[self.controller.pk, self.j1.pk]),
                         {'designator': 'J1', 'used': 'd-sub 9 plug / SOCKET'})
        self.j1.refresh_from_db()
        self.assertEqual(self.j1.used, socket)
        self.assertContains(self.client.get(reverse('devices:connector_edit', args=[self.controller.pk, self.j1.pk])),
                            'value="D-sub 9 plug / socket"')
