"""A family's connector: made from a ready-made face, changed by hand in the editor (checked, the outline fitted again),
its pin and socket branches made with it, the socket side mirrored, an outline of its own; what devices and harnesses draw comes from it."""
import json

from django.urls import reverse

from inventory.faces import drawn, face_of, start
from inventory.models import Branch, Family, Part
from inventory.tests.test_inventory import Base


class ConnectorTests(Base):
    def test_made_from_a_d_sub_with_its_branches(self):
        family = Family.objects.create(name='D-sub 15')
        Branch.objects.create(family=family, name='Pin')                                   # named so: marked so
        url = reverse('inventory:connector', args=[family.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {'action': 'start', 'kind': 'staggered', 'positions': '15'})
        family.refresh_from_db()
        self.assertEqual((family.face['shape'], len(family.face['contacts'])), ('dsub', 15))
        self.assertEqual(sorted(family.branches.values_list('name', 'contacts')), [('Pin', 'pin'), ('socket', 'socket')])
        page = self.client.get(family.get_absolute_url())
        self.assertContains(page, 'Socket side')
        self.assertContains(page, 'family-faces')

    def test_changed_by_hand(self):
        family = Family.objects.create(name='Header 3', face=start('row', 3))
        url = reverse('inventory:connector', args=[family.pk])
        moved = [['A', 100, 100], ['B', 126, 100], ['C', 113, 124]]
        self.client.post(url, {'action': 'save', 'face': json.dumps({'shape': 'circle', 'contacts': moved})})
        family.refresh_from_db()
        self.assertEqual(family.face['shape'], 'circle')
        self.assertEqual([c[0] for c in family.face['contacts']], ['A', 'B', 'C'])
        self.assertEqual(family.face['w'], family.face['h'])                                 # round: as wide as high
        self.assertGreaterEqual(min(c[1] for c in family.face['contacts']), 26)            # moved inside the outline
        self.client.post(url, {'action': 'save', 'face': json.dumps({'shape': 'rect', 'contacts': [['1', 0, 0], ['1', 26, 0]]})})
        family.refresh_from_db()
        self.assertEqual(family.face['shape'], 'circle')                                     # contact 1 twice: refused
        self.client.post(url, {'action': 'save', 'face': 'nonsense'})
        family.refresh_from_db()
        self.assertEqual(len(family.face['contacts']), 3)

    def test_an_outline_of_its_own(self):
        from inventory.faces import mirrored
        family = Family.objects.create(name='Keyed 2')
        url = reverse('inventory:connector', args=[family.pk])
        corners = [[-26, -26], [52, -26], [52, 26], [13, 52], [-26, 26]]
        self.client.post(url, {'action': 'save', 'face': json.dumps({'shape': 'custom', 'contacts': [['1', 0, 0], ['2', 26, 0]],
                                                                     'outline': corners})})
        family.refresh_from_db()
        face = family.face
        self.assertEqual((face['shape'], len(face['outline'])), ('custom', 5))
        self.assertEqual((min(p[0] for p in face['outline']), min(p[1] for p in face['outline'])), (0, 0))   # moved to start at 0
        self.assertEqual(face['contacts'][0][1:], [26, 26])                                  # by whole grid steps, with it
        self.assertEqual(mirrored(face)['outline'][0], [face['w'] - face['outline'][0][0], face['outline'][0][1]])
        self.client.post(url, {'action': 'save', 'face': json.dumps({'shape': 'custom', 'contacts': [], 'outline': [[0, 0], [1, 1]]})})
        family.refresh_from_db()
        self.assertEqual(len(family.face['outline']), 5)                                     # 2 corners: refused

    def test_what_is_drawn_comes_from_the_family(self):
        family = Family.objects.create(name='D-sub 9', face=start('staggered', 9))
        socket = Branch.objects.create(family=family, name='socket', contacts='socket')
        plug = Part.objects.create(number='P-9', family=family)
        recept = Part.objects.create(number='R-9', family=family, branch=socket)
        self.assertEqual(face_of(plug), family.face)
        first = family.face['contacts'][0]
        self.assertEqual(face_of(recept)['contacts'][0], ['1', family.face['w'] - first[1], first[2]])   # mirrored
        self.assertEqual(face_of(socket), face_of(recept))
        self.assertIsNone(face_of(Part.objects.create(number='LOOSE')))
        extra = drawn(plug, ['1', '2', 'S'])                                                 # a pin not on the face: below it
        self.assertEqual(extra['contacts'][-1][0], 'S')
        self.assertEqual(extra['below'], family.face['h'])
        self.assertEqual([c[0] for c in drawn(None, ['1', '4'])['contacts']], ['1', '2', '3', '4'])
