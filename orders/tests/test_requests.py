"""Two ways to make an order: one's own (vendor first, then the lines), or a request describing what is needed for
someone else to order: who is asked hears of it (the administrators when nobody is picked), adds the lines and places it,
and who asked hears it is ordered. Finding a part to add, by words and category."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from inventory.models import Part
from inventory.tests.test_inventory import Base
from orders import service
from orders.models import Order
from web.models import Notification


class RequestTests(Base):
    def test_the_new_order_page_offers_both_ways(self):
        page = self.client.get(reverse('orders:new'))
        self.assertContains(page, 'Order it yourself')
        self.assertContains(page, 'Ask someone to order')
        response = self.client.post(reverse('orders:new'), {'kind': 'order', 'own-vendor': ''})
        self.assertEqual(response.status_code, 200)                               # one's own order needs its vendor
        self.assertFalse(Order.objects.exists())
        response = self.client.post(reverse('orders:new'), {'kind': 'order', 'own-vendor': self.acme.pk})
        order = Order.objects.get()
        self.assertRedirects(response, reverse('orders:order', args=[order.pk]))
        self.assertEqual((order.kind, order.vendor, order.created_by), ('order', self.acme, self.ada))

    def test_a_request_is_ordered_by_someone_else(self):
        bob = get_user_model().objects.create_user('bob', password='pw')
        carol = get_user_model().objects.create_user('carol', password='pw')
        self.client.force_login(bob)
        self.assertEqual(self.client.post(reverse('orders:new'), {'kind': 'request', 'ask-request': ''}).status_code, 200)
        response = self.client.post(reverse('orders:new'), {'kind': 'request', 'ask-request': '20 cable ties, 200 mm',
                                                            'ask-ask': carol.pk})
        order = Order.objects.get()
        self.assertRedirects(response, reverse('orders:order', args=[order.pk]))
        self.assertEqual((order.kind, order.vendor, order.ask, order.created_by), ('request', None, carol, bob))
        self.assertTrue(Notification.objects.filter(user=carol, message__contains='asks to order: 20 cable ties').exists())
        self.assertFalse(Notification.objects.filter(user=self.ada).exists())    # carol is asked, not the administrators

        self.client.force_login(carol)
        self.assertContains(self.client.get(reverse('orders:list') + '?show=requests'), '20 cable ties')
        self.assertNotContains(self.client.get(reverse('orders:list') + '?show=draft'), order.number)
        page = self.client.get(reverse('orders:order', args=[order.pk]))
        self.assertContains(page, '20 cable ties, 200 mm')
        self.assertContains(page, 'Add item')
        self.client.post(reverse('orders:line_add', args=[order.pk]), {'part': 'DSUB-9-PLUG', 'quantity': '20'})
        with self.assertRaisesMessage(ValidationError, 'Say who PO-0001 is ordered from first.'):
            service.place(order, carol)
        self.client.post(reverse('orders:order', args=[order.pk]), {'request': 'something else', 'vendor': self.acme.pk})
        self.client.post(reverse('orders:place', args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual((order.status, order.vendor), ('ordered', self.acme))
        self.assertEqual(order.request, '20 cable ties, 200 mm')                  # what was asked for stays as it was sent
        self.assertTrue(Notification.objects.filter(user=bob, message__contains='ordered from Acme').exists())

        line = order.lines.get()
        self.client.post(reverse('orders:receive', args=[order.pk]), {f'q_{line.pk}': '20', f'l_{line.pk}': self.shelf.pk})
        self.assertEqual(Order.objects.get(pk=order.pk).status, 'received')
        self.assertContains(self.client.get(reverse('orders:order', args=[order.pk])), '20 cable ties, 200 mm')
        self.assertContains(self.client.get(reverse('orders:list') + '?show=received'), 'Asked for: 20 cable ties')

    def test_nobody_picked_asks_the_administrators(self):
        bob = get_user_model().objects.create_user('bob', password='pw')
        self.client.force_login(bob)
        self.client.post(reverse('orders:new'), {'kind': 'request', 'ask-request': 'A new soldering iron', 'ask-vendor': self.acme.pk})
        self.assertTrue(Notification.objects.filter(user=self.ada, message__contains='A new soldering iron').exists())
        order = Order.objects.get()
        self.client.force_login(self.ada)
        self.assertContains(self.client.get('/'), 'request to order')
        service.cancel(order, self.ada)
        self.assertTrue(Notification.objects.filter(user=bob, message__contains="won't order").exists())

    def test_a_request_is_not_where_a_reorder_goes(self):
        request = Order.objects.create(kind='request', vendor=self.acme, request='Plugs')
        line = service.reorder(self.plug, self.ada)
        self.assertNotEqual(line.order, request)


class FindTests(Base):
    def test_finding_parts_by_words_and_category(self):
        Part.objects.create(number='DSUB-OLD', description='D-sub 9 plug', category=self.dsub, active=False)
        found = self.client.get(reverse('inventory:find'), {'q': 'd-sub plug'}).json()
        self.assertEqual([p['number'] for p in found['parts']], ['DSUB-9-PLUG'])   # not the one no longer used
        self.assertEqual(found['parts'][0]['have'], '0')
        found = self.client.get(reverse('inventory:find'), {'category': self.connectors.pk}).json()
        self.assertEqual([p['number'] for p in found['parts']], ['DSUB-9-PLUG'])   # those under it too
        self.assertEqual(len(self.client.get(reverse('inventory:find')).json()['parts']), 2)
