"""Projects: made, listed by status, and what is in them: wire diagrams and orders (of one project each), devices,
assets and tools (in several)."""
from django.urls import reverse

from assets.models import Asset
from devices.models import Device
from inventory.tests.test_inventory import Base
from orders.models import Order
from projects.models import Project as WireDiagram
from work.models import Project


class ProjectTests(Base):
    def test_a_project_and_what_is_in_it(self):
        response = self.client.post(reverse('work:new'), {'name': 'Burn-in rack', 'code': 'BR', 'status': 'active', 'owner': self.ada.pk})
        project = Project.objects.get()
        self.assertRedirects(response, project.get_absolute_url())
        self.assertEqual(project.get_absolute_url(), f'/projects/{project.pk}/')
        diagram = WireDiagram.objects.create(name='Rack')
        order = Order.objects.create(vendor=self.acme)
        device = Device.objects.create(number='CTRL-1', name='Controller')
        crimper = Asset.objects.create(number='T-1', name='Crimper', kind='tool')
        scope = Asset.objects.create(number='M-1', name='Scope', kind='measuring')
        link = reverse('work:link', args=[project.pk])
        for what, thing in (('diagram', diagram), ('order', order), ('device', device), ('asset', crimper), ('asset', scope)):
            self.client.post(link, {'what': what, 'id': thing.pk})
        page = self.client.get(project.get_absolute_url())
        self.assertEqual([list(page.context[k]) for k in ('diagrams', 'orders', 'devices', 'assets', 'tools')],
                         [[diagram], [order], [device], [scope], [crimper]])
        other = Project.objects.create(name='Test rig')
        self.client.post(reverse('work:link', args=[other.pk]), {'what': 'device', 'id': device.pk})
        self.client.post(reverse('work:link', args=[other.pk]), {'what': 'diagram', 'id': diagram.pk})
        self.assertEqual(set(device.work_projects.all()), {project, other})              # a device: in several
        diagram.refresh_from_db()
        self.assertEqual(diagram.in_project, other)                                       # a wire diagram: in one
        self.client.post(link, {'what': 'device', 'id': device.pk, 'remove': '1'})
        self.assertEqual(list(device.work_projects.all()), [other])
        listed = self.client.get(reverse('work:list'))
        self.assertContains(listed, 'Burn-in rack')
        Project.objects.filter(pk=other.pk).update(status='done')
        self.assertNotContains(self.client.get(reverse('work:list')), 'Test rig')         # active ones first
        self.assertContains(self.client.get(reverse('work:list'), {'status': 'all'}), 'Test rig')

    def test_new_wire_diagrams_and_orders_start_in_the_project(self):
        project = Project.objects.create(name='Burn-in rack')
        page = self.client.get(reverse('projects:new'), {'in_project': project.pk})
        self.assertEqual(page.context['form'].initial['in_project'], str(project.pk))
        page = self.client.get(reverse('orders:new'), {'in_project': project.pk})
        self.assertEqual(page.context['own'].initial['in_project'], str(project.pk))
        self.client.post(reverse('projects:new'), {'name': 'Rack', 'in_project': project.pk})
        self.assertEqual(WireDiagram.objects.get().in_project, project)

    def test_sub_projects(self):
        rack = Project.objects.create(name='Burn-in rack', code='BR')
        response = self.client.post(reverse('work:new') + f'?parent={rack.pk}', {'name': 'Load boards', 'code': 'BR-LB', 'status': 'active', 'parent': rack.pk})
        boards = Project.objects.get(code='BR-LB')
        self.assertEqual(boards.parent, rack)
        self.assertEqual(self.client.get(reverse('work:new'), {'parent': rack.pk}).context['form'].initial['parent'], str(rack.pk))
        deep = Project.objects.create(name='Board rev B', code='BR-LB-B', parent=boards)
        changed = self.client.post(reverse('work:edit', args=[rack.pk]), {'name': 'Burn-in rack', 'status': 'active', 'parent': deep.pk})
        self.assertEqual(changed.status_code, 200)                                          # not under one of its own
        rack.refresh_from_db()
        self.assertIsNone(rack.parent)
        # what the sub-projects have shows on the project too, marked with where it is from
        device = Device.objects.create(number='LB-1', name='Load board')
        deep.devices.add(device)
        tool = Asset.objects.create(number='T-9', name='Crimper', kind='tool')
        boards.assets.add(tool)
        WireDiagram.objects.create(name='Boards', in_project=deep)
        page = self.client.get(rack.get_absolute_url())
        self.assertEqual(list(page.context['children']), [boards])
        self.assertEqual([(d, d.via) for d in page.context['sub_devices']], [(device, deep)])
        self.assertEqual([(t, t.via) for t in page.context['sub_tools']], [(tool, boards)])
        self.assertEqual([d.name for d in page.context['sub_diagrams']], ['Boards'])
        self.assertContains(page, 'BR-LB-B')
        # the list: a tree; a sub-project found stands under the project it is part of
        listed = self.client.get(reverse('work:list'), {'q': 'rev B'})
        self.assertEqual([(p.name, p.depth, p.matched) for p in listed.context['projects']],
                         [('Burn-in rack', 0, False), ('Load boards', 1, False), ('Board rev B', 2, True)])
