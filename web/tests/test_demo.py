"""Demo data switched on next to real data, and off again: every row it made goes, real data stays as it was, and a
demo row that real data uses by then is kept (and said)."""
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from inventory.models import Location, Part, Vendor
from orders.models import Order, OrderLine
from web import demo
from web.models import DemoRecord


def counts():
    return {m._meta.label: m.objects.count() for m in apps.get_models() if m._meta.app_label not in ('sessions', 'admin', 'contenttypes', 'auth')}


class DemoTests(TestCase):
    def setUp(self):
        self.ada = get_user_model().objects.create_superuser('ada', 'ada@example.com', 'pw')
        self.real = Part.objects.create(number='MY-PART', description='Ours')
        Location.objects.create(name='Our store')
        self.client.force_login(self.ada)

    def test_on_then_off_leaves_real_data_as_it_was(self):
        before = counts()
        demo.switch_on(self.ada)
        self.assertTrue(demo.is_on())
        self.assertTrue(Part.objects.filter(number='DSUB-9-PLUG').exists())
        with self.assertRaisesMessage(ValidationError, 'on already'):
            demo.switch_on(self.ada)
        self.assertEqual(demo.switch_off(), [])
        after = counts()
        after.pop('web.DemoRecord')
        before.pop('web.DemoRecord')
        self.assertEqual(after, before)
        self.assertTrue(Part.objects.filter(pk=self.real.pk).exists())
        self.assertFalse(demo.is_on())

    def test_what_real_data_uses_is_kept(self):
        demo.switch_on(self.ada)
        real_vendor = Vendor.objects.create(name='Our vendor')
        order = Order.objects.create(vendor=real_vendor)
        OrderLine.objects.create(order=order, part=Part.objects.get(number='TIE-100'), quantity=5)
        kept = demo.switch_off()
        self.assertEqual(kept, ['TIE-100'])
        self.assertFalse(Part.objects.filter(number='DSUB-9-PLUG').exists())
        self.assertFalse(DemoRecord.objects.exists())

    def test_names_already_taken_are_refused(self):
        Part.objects.create(number='DSUB-9-PLUG')
        with self.assertRaisesMessage(ValidationError, "can't go in"):
            demo.switch_on(self.ada)
        self.assertFalse(DemoRecord.objects.exists())
        self.assertFalse(Part.objects.filter(number='TIE-100').exists())

    def test_the_page_is_for_administrators(self):
        self.client.post(reverse('web:demo'), {'action': 'on'})
        self.assertContains(self.client.get(reverse('web:demo')), 'Switch it off')
        self.client.post(reverse('web:demo'), {'action': 'off'})
        self.assertFalse(demo.is_on())
        self.client.force_login(get_user_model().objects.create_user('bob'))
        self.assertEqual(self.client.get(reverse('web:demo')).status_code, 404)
