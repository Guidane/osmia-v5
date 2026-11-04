"""Devices: connectors made with their pins, pins edited as a table, versions saved and restored (what harnesses
plug into keeps its connector), its units (assets), Excel."""
from django.core.exceptions import ValidationError
from django.urls import reverse

from devices.models import Connector, Device, Pin
from inventory.tests.test_inventory import Base
from web import versions


class DeviceBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.controller = Device.objects.create(number='CTRL-1', name='Controller')
        cls.j1 = Connector.objects.create(device=cls.controller, designator='J1', name='Bus', part=cls.plug)
        for number, signal in (('1', '+24 V'), ('2', '0 V'), ('6', 'CAN H'), ('7', 'CAN L')):
            Pin.objects.create(connector=cls.j1, number=number, signal=signal)


class DeviceTests(DeviceBase):
    def test_a_connector_with_its_pins_and_editing_them(self):
        self.client.post(reverse('devices:connector_new', args=[self.controller.pk]), {'designator': 'J2', 'name': 'Power', 'pins': '3'})
        j2 = Connector.objects.get(designator='J2')
        self.assertEqual([p.number for p in j2.ordered_pins()], ['1', '2', '3'])
        page = self.client.post(reverse('devices:connector_new', args=[self.controller.pk]), {'designator': 'j2'})
        self.assertContains(page, 'already has a j2')
        pins = {p.number: p for p in j2.pins.all()}
        self.client.post(reverse('devices:pins', args=[self.controller.pk, j2.pk]), {
            f'number_{pins["1"].pk}': '1', f'signal_{pins["1"].pk}': '+24 V',
            f'set_{pins["1"].pk}': 'PWR', f'set_type_{pins["1"].pk}': 'Twisted',
            f'number_{pins["2"].pk}': '2', f'signal_{pins["2"].pk}': '0 V', f'set_{pins["2"].pk}': 'PWR', f'set_type_{pins["2"].pk}': 'Twisted',
            f'gone_{pins["3"].pk}': 'on',
            'new': '2', 'number_new0': '10', 'signal_new0': 'PE', 'set_type_new0': 'nonsense', 'number_new1': ''})
        self.assertEqual([(p.number, p.signal, p.wire_set, p.set_type) for p in j2.ordered_pins()],
                         [('1', '+24 V', 'PWR', 'Twisted'), ('2', '0 V', 'PWR', 'Twisted'), ('10', 'PE', '', 'Straight')])
        page = self.client.get(reverse('devices:device', args=[self.controller.pk]))
        self.assertContains(page, 'CAN H')

    def test_a_set_has_one_type(self):
        pins = {p.number: p for p in self.j1.pins.all()}
        self.j1.pins.filter(number__in=['6', '7']).update(wire_set='CAN', set_type='Twisted')
        post = {f'number_{p.pk}': p.number for p in pins.values()}
        post.update({f'set_{pins["6"].pk}': 'CAN', f'set_type_{pins["6"].pk}': 'Twisted',
                     f'set_{pins["7"].pk}': 'CAN', f'set_type_{pins["7"].pk}': 'Shielded twisted',      # changed on one
                     f'set_{pins["1"].pk}': 'CAN', f'set_type_{pins["1"].pk}': 'Straight',              # put into it
                     'new': '1', 'number_new0': '8', 'set_new0': '+'})
        self.client.post(reverse('devices:pins', args=[self.controller.pk, self.j1.pk]), post)
        self.assertEqual({p.number: (p.wire_set, p.set_type) for p in self.j1.pins.all()},
                         {'1': ('CAN', 'Shielded twisted'), '2': ('', 'Straight'), '6': ('CAN', 'Shielded twisted'),
                          '7': ('CAN', 'Shielded twisted'), '8': ('', 'Straight')})

    def test_connectors_copied_from_another_device(self):
        other = Device.objects.create(number='CTRL-2', name='Other controller')
        Connector.objects.create(device=other, designator='J1', name='Mine')
        self.j1.pins.filter(number='6').update(wire_set='CAN', set_type='Twisted')
        page = self.client.get(reverse('devices:connectors_copy', args=[other.pk]))
        self.assertContains(page, 'CTRL-1')
        self.assertContains(page, '4 pins')
        self.client.post(reverse('devices:connectors_copy', args=[other.pk]), {'connector': [self.j1.pk]})
        copied = other.connectors.get(designator='J2')                          # J1 was taken
        self.assertEqual((copied.name, copied.part), ('Bus', self.plug))
        self.assertEqual(sorted((p.number, p.signal, p.wire_set) for p in copied.pins.all()),
                         [('1', '+24 V', ''), ('2', '0 V', ''), ('6', 'CAN H', 'CAN'), ('7', 'CAN L', '')])
        self.assertEqual(self.j1.pins.count(), 4)                                 # the original stays

    def test_versions_saved_and_restored(self):
        v1 = versions.save(self.controller, self.ada, 'first')
        self.assertEqual((v1.number, self.controller.version), (1, 1))
        with self.assertRaisesMessage(ValidationError, 'Nothing changed since v1.'):
            versions.save(self.controller, self.ada)
        Pin.objects.filter(connector=self.j1, number='6').update(signal='CAN HIGH')
        Pin.objects.filter(connector=self.j1, number='7').delete()
        Connector.objects.create(device=self.controller, designator='J9')
        self.assertTrue(versions.changed(self.controller))
        self.client.post(reverse('devices:restore', args=[self.controller.pk, 1]))
        self.assertFalse(versions.changed(self.controller))
        self.assertEqual(Connector.objects.get(pk=self.j1.pk).pins.get(number='6').signal, 'CAN H')   # the same connector
        self.assertFalse(Connector.objects.filter(designator='J9').exists())
        page = self.client.get(reverse('devices:version', args=[self.controller.pk, 1]))
        self.assertContains(page, 'CAN L')

    def test_units_are_assets(self):
        from assets.models import Asset
        versions.save(self.controller, self.ada)
        page = self.client.get(reverse('devices:device', args=[self.controller.pk]))
        self.assertContains(page, f'device={self.controller.pk}')                # "Add one" starts an asset for it
        form = self.client.get(reverse('assets:new'), {'kind': 'device', 'device': self.controller.pk, 'number': 'CTRL-1-001', 'version': 1})
        self.assertContains(form, 'value="CTRL-1-001"')
        Asset.objects.create(number='CTRL-1-001', name='Controller', kind='device', device=self.controller, version=1, serial='C-0001')
        self.assertContains(self.client.get(reverse('devices:device', args=[self.controller.pk])), 'C-0001')

    def test_excel(self):
        from io import BytesIO

        from openpyxl import load_workbook
        response = self.client.get(reverse('devices:list'), {'export': 1})
        book = load_workbook(BytesIO(response.content))
        rows = list(book['Pins'].values)
        self.assertEqual(rows[0][:5], ('Device', 'Connector', 'Connector name', 'Connector part', 'Pin'))
        self.assertIn(('CTRL-1', 'J1', 'Bus', 'DSUB-9-PLUG', '6', 'CAN H', None, None, None), rows)
