"""Category attributes: they trickle down the tree, each kind takes only what fits (text, whole numbers, numbers,
a choice from a list, yes/no), parts fill them in on their form, the parts list shows and filters by them, and
changing an attribute is refused while values wouldn't fit any more."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from inventory.models import Attribute, Part, PartValue

from .test_inventory import Base


class AttributeBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        A = Attribute.Kind
        cls.positions = Attribute.objects.create(category=cls.connectors, name='Positions', kind=A.INTEGER, required=True)
        cls.gender = Attribute.objects.create(category=cls.connectors, name='Gender', kind=A.CHOICE, choices='male\nfemale', position=1)
        cls.mounting = Attribute.objects.create(category=cls.dsub, name='Mounting', kind=A.CHOICE, choices='cable\npanel')
        cls.pitch = Attribute.objects.create(category=cls.dsub, name='Pitch', kind=A.DECIMAL, unit='mm', position=1)
        cls.shielded = Attribute.objects.create(category=cls.dsub, name='Shielded', kind=A.YESNO, position=2)

    def form(self, number, category, **attributes):
        data = {'number': number, 'unit': 'pcs', 'category': category.pk, 'minimum': 0, 'reorder_quantity': 0, 'active': 'on',
                'attributes_of': category.pk}
        data.update({f'attr_{k}': v for k, v in attributes.items()})
        return data


class TrickleDownTests(AttributeBase):
    def test_a_category_has_its_own_and_those_from_above(self):
        self.assertEqual([a.name for a in self.dsub.all_attributes()], ['Positions', 'Gender', 'Mounting', 'Pitch', 'Shielded'])
        self.assertEqual([a.name for a in self.connectors.all_attributes()], ['Positions', 'Gender'])

    def test_each_kind_takes_what_fits(self):
        self.assertEqual(self.positions.clean_value(' 9 '), ('9', Decimal(9)))
        self.assertEqual(self.pitch.clean_value('2,77'), ('2.77', Decimal('2.77')))
        self.assertEqual(self.gender.clean_value('MALE'), ('male', None))
        self.assertEqual(self.shielded.clean_value('yes'), ('Yes', None))
        self.assertEqual(self.pitch.clean_value(''), ('', None))
        for attribute, bad in ((self.positions, '9.5'), (self.positions, 'nine'), (self.pitch, 'inf'), (self.gender, 'both'), (self.shielded, 'maybe')):
            with self.assertRaises(ValidationError):
                attribute.clean_value(bad)

    def test_names_are_unique_up_and_down_the_tree(self):
        page = self.client.post(reverse('inventory:attribute_new', args=[self.dsub.pk]), {'name': 'gender', 'kind': 'text'})
        self.assertContains(page, 'Connectors already has an attribute')
        page = self.client.post(reverse('inventory:attribute_new', args=[self.connectors.pk]), {'name': 'Pitch', 'kind': 'text'})
        self.assertContains(page, 'D-sub already has an attribute')
        page = self.client.post(reverse('inventory:attribute_new', args=[self.dsub.pk]), {'name': 'Plating', 'kind': 'choice'})
        self.assertContains(page, 'List the choices')


class PartFormTests(AttributeBase):
    def test_a_part_fills_in_its_category_s_attributes(self):
        response = self.client.post(reverse('inventory:part_new'), self.form('DSUB-25', self.dsub, **{
            str(self.positions.pk): '25', str(self.gender.pk): 'female', str(self.pitch.pk): '2.77', str(self.shielded.pk): 'No'}))
        part = Part.objects.get(number='DSUB-25')
        self.assertRedirects(response, reverse('inventory:part', args=[part.pk]))
        self.assertEqual({v.attribute.name: v.value for v in part.values.all()}, {'Positions': '25', 'Gender': 'female', 'Pitch': '2.77', 'Shielded': 'No'})
        page = self.client.get(reverse('inventory:part', args=[part.pk]))
        self.assertContains(page, '2.77 mm')

    def test_editing_a_part_keeps_its_category(self):
        Part.objects.filter(pk=self.plug.pk).update(category=self.dsub)
        page = self.client.get(reverse('inventory:part_edit', args=[self.plug.pk]))
        self.assertContains(page, f'<option value="{self.dsub.pk}" selected>', html=False)
        self.assertContains(page, 'Mounting')
        page = self.client.get(reverse('inventory:part_new'), {'category': self.dsub.pk})
        self.assertContains(page, f'<option value="{self.dsub.pk}" selected>', html=False)

    def test_what_doesn_t_fit_or_is_missing_is_refused(self):
        page = self.client.post(reverse('inventory:part_new'), self.form('DSUB-X', self.dsub, **{str(self.pitch.pk): 'wide'}))
        self.assertContains(page, '&quot;wide&quot; is not a number')
        self.assertContains(page, 'This field is required')                     # Positions
        self.assertFalse(Part.objects.filter(number='DSUB-X').exists())

    def test_picking_another_category_shows_its_attributes_first(self):
        data = self.form('NEW-1', self.dsub)
        data['attributes_of'] = ''                                                # the form showed no category's yet
        page = self.client.post(reverse('inventory:part_new'), data | {'refresh': '1'})
        self.assertContains(page, 'Mounting')
        self.assertFalse(Part.objects.filter(number='NEW-1').exists())
        data.pop('attributes_of')
        self.client.post(reverse('inventory:part_new'), data)                   # just picked: not refused for Positions
        self.assertTrue(Part.objects.filter(number='NEW-1').exists())

    def test_moving_a_part_to_another_category_drops_what_no_longer_applies(self):
        PartValue.objects.create(part=self.plug, attribute=self.mounting, value='cable')
        PartValue.objects.create(part=self.plug, attribute=self.positions, value='9', number=9)
        self.client.post(reverse('inventory:part_edit', args=[self.plug.pk]), self.form('DSUB-9-PLUG', self.connectors, **{str(self.positions.pk): '9'}))
        self.assertEqual([v.attribute.name for v in self.plug.values.all()], ['Positions'])


class ListTests(AttributeBase):
    def test_the_list_shows_and_filters_by_attributes(self):
        recept = Part.objects.create(number='DSUB-9-RECEPT', category=self.dsub)
        for part, positions, gender in ((self.plug, 9, 'male'), (recept, 9, 'female')):
            PartValue.objects.create(part=part, attribute=self.positions, value=str(positions), number=positions)
            PartValue.objects.create(part=part, attribute=self.gender, value=gender)
        big = Part.objects.create(number='DSUB-25-PLUG', category=self.dsub)
        PartValue.objects.create(part=big, attribute=self.positions, value='25', number=25)
        url = reverse('inventory:parts')
        page = self.client.get(url, {'category': self.connectors.pk})
        self.assertContains(page, '<th>Positions</th>', html=True)
        page = self.client.get(url, {'category': self.dsub.pk, f'a{self.gender.pk}': 'female'})
        self.assertContains(page, 'DSUB-9-RECEPT')
        self.assertNotContains(page, 'DSUB-9-PLUG<')
        page = self.client.get(url, {'category': self.dsub.pk, f'a{self.positions.pk}_min': '10'})
        self.assertContains(page, 'DSUB-25-PLUG')
        self.assertNotContains(page, 'DSUB-9-RECEPT')


class ChangingAttributesTests(AttributeBase):
    def test_a_change_that_values_wouldn_t_fit_is_refused(self):
        PartValue.objects.create(part=self.plug, attribute=self.gender, value='male')
        url = reverse('inventory:attribute_edit', args=[self.connectors.pk, self.gender.pk])
        page = self.client.post(url, {'name': 'Gender', 'kind': 'choice', 'choices': 'M\nF'})
        self.assertContains(page, 'DSUB-9-PLUG: &quot;male&quot;')
        self.client.post(url, {'name': 'Gender', 'kind': 'text'})               # text takes anything
        self.assertEqual(Attribute.objects.get(pk=self.gender.pk).kind, 'text')
        PartValue.objects.create(part=self.plug, attribute=self.pitch, value='2.50', number=Decimal('2.5'))
        self.client.post(reverse('inventory:attribute_edit', args=[self.dsub.pk, self.pitch.pk]), {'name': 'Pitch', 'kind': 'text', 'unit': 'mm'})
        self.assertEqual(PartValue.objects.get(attribute=self.pitch).number, None)

    def test_categories_page_and_excel(self):
        page = self.client.get(reverse('inventory:category', args=[self.dsub.pk]))
        self.assertContains(page, 'from <a href="/categories/%d/#attributes">Connectors</a>' % self.connectors.pk, html=False)
        from io import BytesIO

        from openpyxl import load_workbook
        PartValue.objects.create(part=self.plug, attribute=self.positions, value='9', number=9)
        book = load_workbook(BytesIO(self.client.get(reverse('inventory:parts'), {'export': 1}).content))
        self.assertIn(('DSUB-9-PLUG', 'Connectors / D-sub', 'Positions', 9, None), [tuple(r) for r in book['Attributes'].values])
