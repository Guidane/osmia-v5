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

    def test_made_from_a_connector_made_often(self):
        family = Family.objects.create(name='HD 44')
        url = reverse('inventory:connector', args=[family.pk])
        self.assertContains(self.client.get(url), 'D-sub HD 44 (DB-44)')
        self.client.post(url, {'action': 'start', 'kind': 'hd-44', 'positions': '3'})        # its own size, not 3
        family.refresh_from_db()
        self.assertEqual((family.face['shape'], len(family.face['contacts'])), ('dsub', 44))
        self.assertEqual(len({c[2] for c in family.face['contacts']}), 3)                   # in three rows
        self.client.post(url, {'action': 'start', 'kind': 'gecko-10'})
        family.refresh_from_db()
        contacts = {c[0]: c[1:] for c in family.face['contacts']}
        self.assertEqual(contacts['1'][0], contacts['6'][0])                                # the top row, then the bottom one
        self.assertLess(contacts['1'][1], contacts['6'][1])
        self.assertEqual((family.face['shape'], len(family.face['outline'])), ('custom', 13))   # its notches and key

    def test_standard_connectors_as_families(self):
        from inventory.faces import PRESETS
        mine = Family.objects.create(name='gecko 6')                                         # there already: filled in
        self.client.post(reverse('inventory:families_standard'))
        self.assertEqual(Family.objects.count(), len(PRESETS))
        mine.refresh_from_db()
        self.assertEqual((mine.group.name, len(mine.face['contacts']), mine.branches.count()), ('Gecko', 6, 2))
        hd = Family.objects.get(name='D-sub HD 44')
        self.assertEqual((hd.group.name, len(hd.face['contacts'])), ('D-sub HD', 44))
        self.assertEqual(sorted(hd.branches.values_list('contacts', flat=True)), ['pin', 'socket'])
        self.client.post(reverse('inventory:families_standard'))                             # again: nothing more
        self.assertEqual(Family.objects.count(), len(PRESETS))
        ring = Family.objects.get(name='Ring terminal M4')                                   # a terminal: no sides
        self.assertEqual((ring.group.name, ring.group.parent.name, ring.branches.count()), ('Ring', 'Terminals', 0))
        from inventory.picker import genders
        self.assertEqual(genders(ring), [])
        self.assertEqual([g['name'] for g in genders(Family.objects.get(name='Flat terminal 6.3'))], ['pin', 'socket'])   # a blade: tab and receptacle
        m12 = Family.objects.get(name='M12 5-pin')
        self.assertEqual((m12.group.name, m12.group.parent.name, len(m12.face['contacts'])), ('M12', 'Circular', 5))

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

    def test_families_in_branches(self):
        from inventory.models import FamilyBranch
        url = reverse('inventory:families')
        self.client.post(url, {'form': 'branch', 'branch-name': 'Circular'})
        circular = FamilyBranch.objects.get()
        self.client.post(url, {'form': 'branch', 'branch-name': 'M12', 'branch-parent': circular.pk})
        m12 = FamilyBranch.objects.get(name='M12')
        self.assertEqual(m12.path, 'Circular / M12')
        self.assertContains(self.client.post(f'{url}?branch={circular.pk}', {'form': 'branch', 'branch-name': 'Circular',
                                                                           'branch-parent': m12.pk}), "under itself")
        self.client.post(url, {'form': 'family', 'family-name': 'M12 5-pin', 'family-group': m12.pk})
        family = Family.objects.get(name='M12 5-pin')
        self.assertEqual(family.group, m12)
        self.assertContains(self.client.get(url), 'M12 5-pin')
        self.assertEqual(sorted(circular.below()), sorted([circular.pk, m12.pk]))         # picking Circular shows it

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
