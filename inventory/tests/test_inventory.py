"""Parts and stock: adding, moving, using and counting stock keeps a movement each and never goes below zero; finding
parts; a part's page; locations and categories as trees."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from inventory import stock
from inventory.models import Category, Location, Movement, Part, Stock, Vendor


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ada = get_user_model().objects.create_superuser('ada', 'ada@example.com', 'pw', first_name='Ada')
        cls.store = Location.objects.create(name='Store')
        cls.shelf = Location.objects.create(name='Shelf 1', parent=cls.store)
        cls.bench = Location.objects.create(name='Bench')
        cls.acme = Vendor.objects.create(name='Acme')
        cls.connectors = Category.objects.create(name='Connectors')
        cls.dsub = Category.objects.create(name='D-sub', parent=cls.connectors)
        cls.plug = Part.objects.create(number='DSUB-9-PLUG', description='D-sub 9 plug', category=cls.dsub, vendor=cls.acme,
                                       price=Decimal('2.50'), minimum=10)
        cls.wire = Part.objects.create(number='WIRE-22-RED', description='Wire 22 AWG red', unit='m')

    def setUp(self):
        self.client.force_login(self.ada)


class StockTests(Base):
    def test_add_move_use_count(self):
        stock.add(self.plug, '25', self.shelf, self.ada, 'found in a box')
        stock.move(self.plug, 5, self.shelf, self.bench, self.ada)
        stock.use(self.plug, '2,5', self.bench, self.ada)                      # a comma works too
        self.assertEqual(self.plug.on_hand, Decimal('22.5'))
        stock.count(self.plug, self.shelf, 18, self.ada)
        self.assertEqual(Stock.objects.get(part=self.plug, location=self.shelf).quantity, 18)
        self.assertEqual([(m.kind, m.quantity) for m in Movement.objects.order_by('pk')],
                         [('added', 25), ('moved', 5), ('used', Decimal('2.5')), ('counted', -2)])

    def test_never_below_zero_and_only_real_quantities(self):
        stock.add(self.plug, 3, self.shelf, self.ada)
        with self.assertRaisesMessage(ValidationError, 'There are only 3 pcs of DSUB-9-PLUG in Store / Shelf 1.'):
            stock.use(self.plug, 4, self.shelf, self.ada)
        for bad in ('0', '-1', 'lots', 'NaN'):
            with self.assertRaises(ValidationError):
                stock.add(self.plug, bad, self.shelf, self.ada)
        with self.assertRaises(ValidationError):
            stock.move(self.plug, 1, self.shelf, self.shelf, self.ada)
        self.assertEqual(self.plug.on_hand, 3)

    def test_from_the_part_s_page(self):
        url = reverse('inventory:part_stock', args=[self.plug.pk])
        self.client.post(url, {'action': 'add', 'quantity': '12', 'location': self.shelf.pk})
        self.client.post(url, {'action': 'move', 'quantity': '2', 'location': self.shelf.pk, 'to': self.bench.pk})
        response = self.client.post(url, {'action': 'use', 'quantity': '99', 'location': self.bench.pk}, follow=True)
        self.assertContains(response, 'There are only 2 pcs')
        page = self.client.get(reverse('inventory:part', args=[self.plug.pk]))
        self.assertContains(page, 'Store / Shelf 1')
        self.assertContains(page, '<b>12</b>', html=False)                       # on hand, written plainly (not 1.2E+1)
        self.assertContains(page, 'Moved <b>2</b>')


class FindingTests(Base):
    def test_search_category_and_one_match_goes_straight_to_it(self):
        page = self.client.get(reverse('inventory:parts'), {'q': 'plug'})
        self.assertRedirects(page, reverse('inventory:part', args=[self.plug.pk]))
        page = self.client.get(reverse('inventory:parts'), {'category': self.connectors.pk})   # the categories under it too
        self.assertContains(page, 'DSUB-9-PLUG')
        self.assertNotContains(page, 'WIRE-22-RED')
        Part.objects.filter(pk=self.wire.pk).update(active=False)
        self.assertNotContains(self.client.get(reverse('inventory:parts')), 'WIRE-22-RED')
        self.assertContains(self.client.get(reverse('inventory:parts'), {'all': 1}), 'WIRE-22-RED')

    def test_making_and_changing_a_part(self):
        response = self.client.post(reverse('inventory:part_new'), {
            'number': 'TIE-100', 'description': 'Cable tie', 'unit': 'pcs', 'category': self.connectors.pk,
            'minimum': '0', 'reorder_quantity': '0', 'active': 'on'})
        tie = Part.objects.get(number='TIE-100')
        self.assertRedirects(response, reverse('inventory:part', args=[tie.pk]))
        page = self.client.post(reverse('inventory:part_new'), {'number': 'tie-100', 'unit': 'pcs', 'minimum': 0, 'reorder_quantity': 0})
        self.assertEqual(Part.objects.filter(number__iexact='tie-100').count(), 1)
        self.assertEqual(page.status_code, 200)


class TreeTests(Base):
    def test_locations_show_what_is_in_them_and_below(self):
        stock.add(self.plug, 4, self.shelf, self.ada)
        page = self.client.get(reverse('inventory:location', args=[self.store.pk]))
        self.assertContains(page, 'DSUB-9-PLUG')                                # on a shelf inside it
        self.assertContains(self.client.get(reverse('inventory:locations')), 'Shelf 1')

    def test_nothing_inside_itself(self):
        page = self.client.post(reverse('inventory:location_edit', args=[self.store.pk]), {'name': 'Store', 'parent': self.shelf.pk})
        self.assertContains(page, 'inside itself')
        page = self.client.post(reverse('inventory:categories') + f'?edit={self.connectors.pk}', {'name': 'Connectors', 'parent': self.dsub.pk})
        self.assertContains(page, 'part of itself')
