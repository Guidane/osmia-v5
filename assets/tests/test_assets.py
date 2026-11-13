"""Assets: checked out and back, calibration (due after its interval, overdue on Home), sent away, in use and retired;
the list by kind and category; categories of their own (not parts'), with attributes (an auto number counting through
the tree); a tool linking to the parts it crimps."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse

from assets import service
from assets.models import Asset
from inventory.models import Attribute, Category, Part
from inventory.tests.test_inventory import Base


class AssetTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.tools = Category.objects.create(name='Crimp tools', kind='assets')
        cls.tool = Asset.objects.create(number='T-001', name='D-sub crimp tool', kind='tool', category=cls.tools,
                                        calibration_months=12, calibrated_on=date(2025, 1, 31), keeper=cls.ada)

    def test_checked_out_and_back(self):
        self.client.post(reverse('assets:act', args=[self.tool.pk]), {'action': 'out', 'to': self.ada.pk, 'note': 'harness H-0001'})
        tool = Asset.objects.get()
        self.assertEqual((tool.status, tool.holder), ('out', self.ada))
        with self.assertRaisesMessage(ValidationError, 'is checked out (Ada)'):
            service.check_out(tool, self.ada)
        with self.assertRaisesMessage(ValidationError, 'bring it back first'):
            service.send_away(tool, self.ada, Asset.Status.REPAIR)
        self.client.post(reverse('assets:act', args=[self.tool.pk]), {'action': 'back'})
        tool.refresh_from_db()
        self.assertEqual((tool.status, tool.holder), ('available', None))
        self.assertContains(self.client.get(reverse('assets:asset', args=[tool.pk])), 'to Ada: harness H-0001')
        service.send_away(tool, self.ada, Asset.Status.IN_USE, 'in the burn-in rack')
        self.assertEqual(Asset.objects.get().status, 'in_use')

    def test_calibration_due_and_overdue(self):
        self.assertEqual(self.tool.calibration_due, date(2026, 1, 31))
        Asset.objects.filter(pk=self.tool.pk).update(calibrated_on=date(2024, 3, 31), calibration_months=11)
        self.assertEqual(Asset.objects.get().calibration_due, date(2025, 2, 28))   # the end of a shorter month
        self.assertContains(self.client.get('/'), '1</b> asset due for calibration')
        service.send_away(self.tool, self.ada, Asset.Status.CALIBRATION)
        self.client.post(reverse('assets:act', args=[self.tool.pk]), {'action': 'calibrated', 'on': str(date.today())})
        tool = Asset.objects.get()
        self.assertEqual((tool.status, tool.calibrated_on), ('available', date.today()))
        with self.assertRaises(ValidationError):
            service.calibrated(tool, self.ada, date.today() + timedelta(days=1))

    def test_the_list_by_words_and_category_and_retiring(self):
        Asset.objects.create(number='PSU-01', name='Lab power supply', kind='lab')
        page = self.client.get(reverse('assets:list'), {'q': 'power lab'})
        self.assertContains(page, 'PSU-01')
        self.assertNotContains(page, 'T-001')
        self.assertContains(self.client.get(reverse('assets:list'), {'q': 'crimp tools'}), 'T-001')   # its category's name
        Asset.objects.filter(pk=self.tool.pk).update(asset_number='FIN-2026-0042')
        self.assertContains(self.client.get(reverse('assets:list'), {'q': 'fin-2026'}), 'T-001')   # its asset number
        self.assertContains(self.client.get(reverse('assets:asset', args=[self.tool.pk])), 'FIN-2026-0042')
        page = self.client.get(reverse('assets:asset', args=[self.tool.pk]))
        self.assertContains(page, 'data-notes-form')                                        # a Notes card, even empty
        back = self.client.post(reverse('web:notes', args=['asset', self.tool.pk]), {'notes': ' Keep it oiled. ', 'next': '/assets/'})
        self.assertRedirects(back, '/assets/', fetch_redirect_response=False)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.notes, 'Keep it oiled.')
        self.assertEqual(self.client.post(reverse('web:notes', args=['nothing', 1]), {'notes': 'x'}).status_code, 404)
        page = self.client.get(reverse('assets:list'), {'category': self.tools.pk})
        self.assertContains(page, 'T-001')
        self.assertNotContains(page, 'PSU-01')
        counts = {c.pk: n for c, _, n in page.context['categories']}                     # the tree: each with what is under it
        self.assertEqual(counts[self.tools.pk], 1)
        picked = self.client.get(reverse('assets:list'), {'asset': self.tool.pk})        # its details beside the list
        self.assertEqual(picked.context['brief']['asset'], self.tool)
        self.assertContains(self.client.get(reverse('assets:brief', args=[self.tool.pk])), self.tool.name)
        service.send_away(self.tool, self.ada, Asset.Status.RETIRED)
        self.assertNotContains(self.client.get(reverse('assets:list')), 'T-001')
        self.assertContains(self.client.get(reverse('assets:list'), {'status': 'retired'}), 'T-001')
        self.assertEqual(service.due(), [])


class AssetCategoryTests(Base):
    """Assets have categories of their own, with attributes as parts' have (linking to parts too)."""
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.workshop = Category.objects.create(name='Workshop', kind='assets')
        cls.crimpers = Category.objects.create(name='Crimp tools', parent=cls.workshop, kind='assets')

    def test_an_asset_fills_in_its_category_s_attributes_and_links_to_parts(self):
        wire = Attribute.objects.create(category=self.workshop, name='Wire size', kind='decimal', unit='mm²')
        crimps = Attribute.objects.create(category=self.crimpers, name='Crimps', kind='interacts', target=self.dsub, reverse_name='Crimped by')
        tool = Asset.objects.create(number='T-002', name='Crimp tool', category=self.crimpers)
        response = self.client.post(reverse('assets:edit', args=[tool.pk]), {
            'number': 'T-002', 'name': 'Crimp tool', 'kind': 'tool', 'category': self.crimpers.pk, 'attributes_of': self.crimpers.pk,
            f'attr_{wire.pk}': '0,5', f'attr_{crimps.pk}': [self.plug.pk]})
        self.assertRedirects(response, reverse('assets:asset', args=[tool.pk]))
        self.assertContains(self.client.get(reverse('assets:asset', args=[tool.pk])), '0.5 mm²')
        self.assertContains(self.client.get(reverse('inventory:part', args=[self.plug.pk])), 'Crimped by')
        self.assertContains(self.client.get(reverse('inventory:category', args=[self.workshop.pk])), '1 asset')
        self.assertContains(self.client.get(reverse('assets:list'), {'category': self.workshop.pk, f'a{wire.pk}_min': '0.4'}), 'T-002')

    def test_each_has_its_own_tree(self):
        page = self.client.get(reverse('assets:new'))
        self.assertContains(page, 'Crimp tools')
        self.assertNotContains(page, 'D-sub')
        self.assertNotContains(self.client.get(reverse('inventory:part_new')), 'Crimp tools')
        response = self.client.post(reverse('assets:new'), {'number': 'T-009', 'name': 'Meter', 'kind': 'measuring', 'category': self.dsub.pk})
        self.assertEqual(response.status_code, 200)                              # a part category is not one of assets
        self.assertFalse(Asset.objects.filter(number='T-009').exists())
        tabs = self.client.get(reverse('inventory:categories'), {'kind': 'assets'})
        self.assertContains(tabs, 'Crimp tools')
        self.assertNotContains(tabs, 'D-sub')
        self.client.post(reverse('inventory:categories') + '?kind=assets', {'name': 'Meters', 'parent': self.workshop.pk})
        self.assertEqual(Category.objects.get(name='Meters').kind, 'assets')
        self.client.post(reverse('inventory:categories') + '?kind=parts', {'name': 'Sleeves', 'parent': self.workshop.pk})
        self.assertFalse(Category.objects.filter(name='Sleeves').exists())        # not under an asset category

    def test_an_auto_number_counts_through_its_tree(self):
        tool = Asset.objects.create(number='T-003', name='Stripper', category=self.crimpers)
        self.client.post(reverse('inventory:attribute_new', args=[self.workshop.pk]),
                         {'name': 'ID', 'kind': 'auto', 'prefix': 'WS-', 'digits': 4})
        self.assertEqual(tool.values.get().value, 'WS-0001')                     # those there already
        self.client.post(reverse('assets:new'), {'number': 'T-004', 'name': 'Cutter', 'kind': 'tool', 'category': self.crimpers.pk,
                                                 'attributes_of': self.crimpers.pk})
        self.assertEqual(Asset.objects.get(number='T-004').values.get().value, 'WS-0002')


class DocumentAndLabelTests(Base):
    def test_labels_of_several_on_a_sheet_and_a_saved_layout(self):
        tie = Part.objects.create(number='TIE-100', description='Cable tie 100 mm')
        url = reverse('web:labels', args=['part'])
        page = self.client.get(url, {'ids': f'{self.plug.pk},{tie.pk}'})
        self.assertContains(page, 'DSUB-9-PLUG')
        self.assertContains(page, 'Cable tie 100 mm')
        self.assertEqual(page.content.decode().count('class="sticker"'), 2)
        self.assertEqual(page.content.decode().count('class="sheet"'), 1)
        page = self.client.get(url, {'ids': tie.pk, 'size': '38x21', 'show_number': '1', 'copies': '70'})
        self.assertNotContains(page, 'Cable tie 100 mm')                      # its description not shown
        self.assertEqual(page.content.decode().count('class="sheet"'), 2)     # 70 labels: two sheets of 65
        self.assertEqual(page.content.decode().count('class="sticker"'), 70)
        self.client.get(url, {'ids': tie.pk, 'size': '99x38', 'show_number': '1', 'save': '1'})
        page = self.client.get(url, {'ids': tie.pk})
        self.assertContains(page, '<option value="99x38" selected>', html=False)
        asset = Asset.objects.create(number='T-010', name='Crimp tool', serial='SN-55')
        page = self.client.get(reverse('web:labels', args=['asset']), {'ids': asset.pk, 'size': '64x38', 'show_number': '1', 'show_serial': '1'})
        self.assertContains(page, 'T-010')
        self.assertContains(page, 'S/N SN-55')


class AssetFieldTests(Base):
    """Asset fields: what every asset fills in, whatever its category (a company's own: an inventory ID, a cost centre)."""
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.tool = Asset.objects.create(number='T-001', name='D-sub crimp tool', kind='tool')

    def test_asset_fields_every_asset_fills_in(self):
        url = reverse('assets:fields')
        self.client.post(url, {'name': 'Inventory ID', 'kind': 'auto', 'prefix': 'INV-', 'digits': '4'})
        ident = Attribute.objects.get(name='Inventory ID')
        self.assertIsNone(ident.category)                                                   # no category: every asset
        self.assertEqual(AssetValueOf(self.tool, ident), 'INV-0001')                        # the ones there already: numbered
        self.client.post(url, {'name': 'Cost centre', 'kind': 'choice', 'choices': 'Lab\nProduction'})
        self.client.post(url, {'name': 'Bought for', 'kind': 'decimal', 'unit': '€'})
        self.assertContains(self.client.post(url, {'name': 'cost centre', 'kind': 'text'}), 'There is already an asset field')
        response = self.client.post(reverse('assets:new'), {'number': 'PSU-02', 'name': 'Bench supply', 'kind': 'lab', 'status': 'available',
                                                            f'attr_{Attribute.objects.get(name="Cost centre").pk}': 'Lab',
                                                            f'attr_{Attribute.objects.get(name="Bought for").pk}': '129,50',
                                                            'attributes_of': ''})
        psu = Asset.objects.get(number='PSU-02')
        self.assertRedirects(response, psu.get_absolute_url())
        self.assertEqual((AssetValueOf(psu, ident), AssetValueOf(psu, Attribute.objects.get(name='Cost centre'))), ('INV-0002', 'Lab'))
        page = self.client.get(psu.get_absolute_url())
        self.assertContains(page, '129.5')
        listed = self.client.get(reverse('assets:list'), {f'a{Attribute.objects.get(name="Cost centre").pk}': 'Lab'})
        self.assertEqual([a.number for a, _ in listed.context['rows']], ['PSU-02'])        # filtered by it, any category
        self.client.post(reverse('assets:field_move', args=[Attribute.objects.get(name='Bought for').pk]), {'to': 'up'})
        self.assertEqual([a.name for a in Attribute.asset_fields()], ['Inventory ID', 'Bought for', 'Cost centre'])
        self.client.post(reverse('assets:field_delete', args=[ident.pk]))
        self.assertFalse(Attribute.objects.filter(name='Inventory ID').exists())


def AssetValueOf(asset, attribute):
    from assets.models import AssetValue
    found = AssetValue.objects.filter(asset=asset, attribute=attribute).first()
    return found.value if found else None
