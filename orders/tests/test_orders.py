"""Orders: reordering a part (onto the vendor's draft), placing, receiving into stock (partly, then all; the maker
hears), what is late, what needs ordering, and cancelling."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from inventory import stock
from inventory.models import Movement, Part
from inventory.tests.test_inventory import Base
from orders import service
from orders.models import Order
from web.models import Notification


class OrderTests(Base):
    def test_reorder_place_and_receive_in_two_parts(self):
        response = self.client.post(reverse('inventory:part_reorder', args=[self.plug.pk]))
        order = Order.objects.get()
        self.assertRedirects(response, reverse('orders:order', args=[order.pk]))
        self.assertEqual((order.number, order.vendor, order.status), ('PO-0001', self.acme, 'draft'))
        line = order.lines.get()
        self.assertEqual((line.quantity, line.price), (10, Decimal('2.50')))     # up to the minimum, at the last price
        service.reorder(self.plug, self.ada)                                     # again: the same draft, more of it
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.lines.get().quantity, 20)

        self.client.post(reverse('orders:place', args=[order.pk]), {'expected_on': str(date.today() + timedelta(days=7))})
        order.refresh_from_db()
        self.assertEqual((order.status, order.ordered_on), ('ordered', date.today()))
        self.assertEqual(service.on_order(self.plug), 20)

        bob = self.make_user('bob')
        self.client.force_login(bob)
        self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '12', f'l_{line.pk}': self.shelf.pk})
        order.refresh_from_db()
        self.assertEqual(order.status, 'partly')
        self.assertEqual(self.plug.on_hand, 12)
        self.assertEqual(service.on_order(self.plug), 8)
        response = self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '9', f'l_{line.pk}': self.shelf.pk}, follow=True)
        self.assertContains(response, 'Only 8 of DSUB-9-PLUG are still to come.')
        self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '8', f'l_{line.pk}': self.bench.pk})
        order.refresh_from_db()
        self.assertEqual((order.status, order.received_on), ('received', date.today()))
        self.assertEqual(self.plug.on_hand, 20)
        self.assertEqual(Movement.objects.filter(kind='received', reference='PO-0001').count(), 2)
        self.assertTrue(Notification.objects.filter(user=self.ada, message__contains='it is complete').exists())   # Ada made it

    def make_user(self, name):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.create_user(name, password='pw')

    def test_what_is_late_and_what_needs_ordering(self):
        self.assertEqual([p for p, _, _ in service.needs_ordering()], [self.plug])
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        order.lines.create(part=self.plug, quantity=10)
        self.assertEqual([p for p, _, _ in service.needs_ordering()], [self.plug])   # a draft isn't coming
        service.place(order, self.ada, date.today() - timedelta(days=1))
        self.assertEqual(service.needs_ordering(), [])                               # on its way
        self.assertTrue(Order.objects.get().overdue)
        home = self.client.get('/')
        self.assertContains(home, 'Late')
        self.assertContains(home, 'PO-0001')
        self.assertContains(self.client.get(reverse('orders:list')), 'Late')

    def test_draft_lines_and_rules(self):
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        with self.assertRaisesMessage(ValidationError, 'has nothing on it yet'):
            service.place(order, self.ada)
        self.client.post(reverse('orders:line_add', args=[order.pk]), {'part': 'wire-22-red', 'quantity': '50'})
        line = order.lines.get()
        self.assertEqual((line.part, line.quantity), (self.wire, 50))
        self.client.post(reverse('orders:line_change', args=[order.pk, line.pk]), {'quantity': '60', 'price': '0.12'})
        line.refresh_from_db()
        self.assertEqual((line.quantity, line.price), (60, Decimal('0.12')))
        service.place(order, self.ada)
        self.assertEqual(Part.objects.get(pk=self.wire.pk).price, Decimal('0.12'))  # the last price
        self.client.post(reverse('orders:line_add', args=[order.pk]), {'part': 'DSUB-9-PLUG', 'quantity': '1'})
        self.assertEqual(order.lines.count(), 1)                                     # placed: lines fixed
        with self.assertRaisesMessage(ValidationError, 'Fill in what arrived.'):
            service.receive(order, [], self.ada)

    def test_cancelling(self):
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        line = order.lines.create(part=self.plug, quantity=10)
        service.place(order, self.ada)
        service.receive(order, [(line, 1, self.shelf)], self.ada)
        with self.assertRaisesMessage(ValidationError, 'can\'t be cancelled any more'):
            service.cancel(order, self.ada)
        other = Order.objects.create(vendor=self.acme)
        service.cancel(other, self.ada)
        self.assertEqual(Order.objects.get(pk=other.pk).status, 'cancelled')

    def test_a_part_without_a_vendor_can_t_be_reordered(self):
        with self.assertRaisesMessage(ValidationError, 'WIRE-22-RED has no vendor'):
            service.reorder(self.wire, self.ada)
        stock.add(self.wire, 5, self.shelf, self.ada)
        self.assertNotContains(self.client.get(reverse('inventory:part', args=[self.wire.pk])), 'Reorder</button>')


class AssetOrderTests(Base):
    def test_an_asset_on_order_is_ordered_and_received(self):
        from assets.models import Asset
        response = self.client.post(reverse('assets:new'), {'number': 'T-009', 'name': 'Crimp tool', 'kind': 'tool', 'vendor': self.acme.pk,
                                                            'price': '250', 'on_order': 'on'})
        tool = Asset.objects.get(number='T-009')
        self.assertEqual(tool.status, 'ordered')
        self.assertRedirects(response, reverse('assets:asset', args=[tool.pk]))
        self.client.post(reverse('assets:act', args=[tool.pk]), {'action': 'order'})
        order = Order.objects.get()
        line = order.lines.get()
        self.assertEqual((line.asset, line.quantity, line.price), (tool, 1, Decimal('250')))
        with self.assertRaisesMessage(ValidationError, 'is on an order already'):
            service.order_asset(tool, self.ada)
        service.reorder(self.plug, self.ada)                                   # a part on the same draft
        self.assertEqual(order.lines.count(), 2)
        service.place(order, self.ada)
        self.assertEqual(service.on_order(self.plug), 10)
        self.assertContains(self.client.get(reverse('orders:order', args=[order.pk])), 'T-009')
        self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '1', f'l_{line.pk}': self.bench.pk})
        tool.refresh_from_db()
        self.assertEqual((tool.status, tool.location), ('available', self.bench))
        self.assertEqual(self.plug.on_hand, 0)                                  # assets don't go into stock
        self.assertEqual(Order.objects.get().status, 'partly')
        self.assertEqual(tool.events.get().kind, 'received')

    def test_an_asset_on_order_is_added_by_its_asset_tag(self):
        from assets.models import Asset
        meter = Asset.objects.create(number='M-002', name='Meter', kind='measuring', status='ordered', vendor=self.acme)
        order = Order.objects.create(vendor=self.acme, created_by=self.ada)
        self.client.post(reverse('orders:line_add', args=[order.pk]), {'part': 'm-002'})
        self.assertEqual(order.lines.get().asset, meter)
        response = self.client.post(reverse('orders:line_add', args=[order.pk]), {'part': 'M-002'}, follow=True)
        self.assertContains(response, 'not an asset waiting to be ordered')
