"""Projects: the list, a project's page (its configurations as a tree, the selected one drawn as devices and the
harnesses between them, its changes and what is wrong), changing a configuration, and what building one needs."""
import json

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import Department
from devices.models import Connector, Device
from harnesses.models import Harness
from inventory.models import choices_of_parts, part_or_family
from orders import service as orders
from web import excel
from web.shortcuts import edit_page, errors
from web.forms import TreeForm, initial_for

from . import configs
from .models import Configuration, HarnessRequest, Project

GRID_X, GRID_Y = 300, 240   # where new devices go on the diagram: a grid of four across


class ProjectForm(TreeForm):
    tree_fields = {'department': Department}

    class Meta:
        model = Project
        fields = ['code', 'name', 'in_project', 'description', 'department', 'owner']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}



def _tree(project):
    """The project's configurations, depth first: [(configuration, depth)]."""
    children = {}
    for c in project.configurations.all():
        children.setdefault(c.parent_id, []).append(c)
    out = []

    def walk(parent, depth):
        for c in children.get(parent, []):
            out.append((c, depth))
            walk(c.pk, depth + 1)
    walk(None, 0)
    return out


@login_required
def project_list(request):
    return render(request, 'projects/list.html', {'projects': Project.objects.prefetch_related('configurations', 'harnesses')})


@login_required
def project_form(request, pk=None):
    item = get_object_or_404(Project, pk=pk) if pk else None
    def first_configuration(project, new):
        if new:
            Configuration.objects.create(project=project, name='Base')
    return edit_page(request, ProjectForm(request.POST or None, instance=item, initial=initial_for(item, owner=request.user.pk, in_project=request.GET.get('in_project'))),
                     'wire diagram', saved=first_configuration)


def _selected(request, project):
    config = project.configurations.filter(pk=request.GET.get('config') or request.POST.get('config') or 0).first()
    return config or project.configurations.filter(parent=None).first() or project.configurations.first()


def _diagram(config, rows, found):
    """What the diagram draws: the devices (with their connectors), the harnesses between them, and (faded) what
    the parent has that this configuration took away."""
    base = configs.resolve(config.parent)
    device_ids = {r['device_id'] for r in list(rows.values()) + list(base.values()) if r['kind'] == 'device'}
    devices = {d.pk: d for d in Device.objects.filter(pk__in=device_ids).prefetch_related('connectors__pins', 'connectors__part',
                                                                                        'connectors__family')}
    harnesses = {h.pk: h for h in Harness.objects.filter(pk__in={r['harness_id'] for r in rows.values() if r['harness_id']})
                 .prefetch_related('ends')}
    bad = {key for key, _ in found}

    def state(key, row):
        before = base.get(key)
        if config.parent_id is None:
            return 'same'
        if before is None:
            return 'added'
        return 'same' if all(before[f] == row[f] for f in ('device_id', 'harness_id', 'label', 'ends')) else 'changed'

    out = {'devices': [], 'harnesses': [], 'ghosts': [],
           'requests': [{'id': r.pk, 'a': r.a, 'b': r.b, 'text': r.request} for r in config.harness_requests.filter(status='open')]}
    for key, row in rows.items():
        if row['kind'] == 'device' and row['device_id'] in devices:
            d = devices[row['device_id']]
            out['devices'].append({'key': key, 'label': row['label'] or d.number, 'number': d.number, 'name': d.name, 'colour': d.colour,
                                   'url': d.get_absolute_url(), 'x': row['x'], 'y': row['y'], 'state': state(key, row),
                                   'connectors': [{'id': c.pk, 'designator': c.designator, 'name': c.name, 'part': c.used_name,
                                                   'side': c.side, 'along': c.along,
                                                   'pins_url': reverse('devices:pins', args=[d.pk, c.pk]),
                                                   'pins': [[p.number, p.signal, p.wire_set, p.set_type if p.wire_set else '', p.description]
                                                            for p in c.ordered_pins()]} for c in d.connectors.all()]})
        elif row['kind'] == 'harness' and row['harness_id'] in harnesses:
            h = harnesses[row['harness_id']]
            out['harnesses'].append({'key': key, 'number': h.number, 'name': h.name, 'url': h.get_absolute_url(), 'state': state(key, row),
                                     'bad': key in bad, 'handles': row['handles'],
                                     'ends': [{'id': str(e.pk), 'designator': e.designator, 'device': configs.spot(row['ends'].get(str(e.pk)))[0],
                                               'connector': configs.spot(row['ends'].get(str(e.pk)))[1]} for e in h.ends.all()]})
    for key, row in base.items():
        if key not in rows and row['kind'] == 'device' and row['device_id'] in devices:
            out['ghosts'].append({'label': row['label'] or devices[row['device_id']].number, 'x': row['x'], 'y': row['y']})
    return out


@login_required
def project(request, pk):
    item = get_object_or_404(Project, pk=pk)
    config = _selected(request, item)
    rows = configs.resolve(config) if config else {}
    found = configs.problems(config, rows) if config else []
    placed_devices = [(key, r) for key, r in rows.items() if r['kind'] == 'device']
    device_names = {d.pk: d for d in Device.objects.filter(pk__in=[r['device_id'] for _, r in placed_devices])}
    harness_rows = []
    for key, r in rows.items():
        if r['kind'] == 'harness':
            h = Harness.objects.filter(pk=r['harness_id']).prefetch_related('ends').first()
            if h:   # each end, and where it plugs in ("device key:connector id")
                harness_rows.append((key, h, [(e, '{}:{}'.format(*configs.spot(r['ends'].get(str(e.pk)))) if configs.spot(r['ends'].get(str(e.pk)))[1] else '')
                                              for e in h.ends.all()]))
    return render(request, 'projects/project.html', {
        'project': item, 'config': config, 'tree': _tree(item), 'changes': configs.changes(config) if config else [],
        'problems': [text for _, text in found],
        'diagram': _diagram(config, rows, found) if config else {'devices': [], 'harnesses': [], 'ghosts': [], 'requests': []},
        'placed_devices': [(key, r, device_names.get(r['device_id'])) for key, r in placed_devices],
        'harness_rows': harness_rows, 'sockets': [(value, label) for value, label, _, _ in configs.sockets(config, rows)] if config else [],
        'devices': Device.objects.all(), 'harnesses': item.harnesses.exclude(status=Harness.Status.OBSOLETE),
        'part_choices': choices_of_parts() if config else [], 'people': get_user_model().objects.filter(is_active=True),
        'requests': [(r, configs.label_of(rows, r.a), configs.label_of(rows, r.b)) for r in
                     config.harness_requests.select_related('created_by', 'ask', 'harness')[:20]] if config else []})


@login_required
@require_POST
def configuration(request, pk):
    """Make, rename, detach or delete a configuration."""
    item = get_object_or_404(Project, pk=pk)
    post = request.POST
    config = item.configurations.filter(pk=post.get('config') or 0).first()
    action = post.get('action')
    try:
        if action == 'new':
            parent = item.configurations.filter(pk=post.get('parent') or 0).first()
            name = post.get('name', '').strip()
            if not name:
                raise ValidationError('Give the configuration a name.')
            if post.get('copy') and parent:
                config = configs.copy(parent, name[:200])
            else:
                config = Configuration.objects.create(project=item, parent=parent, name=name[:200])
        elif config is None:
            raise ValidationError('Pick the configuration.')
        elif action == 'rename':
            config.name = post.get('name', '').strip()[:200] or config.name
            config.description = post.get('description', '').strip()
            config.save()
        elif action == 'detach':
            configs.detach(config)
            messages.success(request, f'{config} is a setup of its own now.')
        elif action == 'delete':
            if config.children.exists():
                raise ValidationError(f'{config} has configurations under it: delete or detach those first.')
            if item.configurations.count() == 1:
                raise ValidationError('A wire diagram keeps at least one configuration.')
            config.delete()
            return redirect(item)
    except ValidationError as exc:
        errors(request, exc)
    return redirect(config.get_absolute_url() if config and config.pk else item.get_absolute_url())


@login_required
@require_POST
def change(request, pk):
    """A change to the selected configuration: add, move, rename, swap or take away a device; add, plug in or take
    away a harness, or make one between two connectors; take a change back. Moves come from the diagram (JSON back)."""
    item = get_object_or_404(Project, pk=pk)
    config = _selected(request, item)
    post, action, key = request.POST, request.POST.get('action'), request.POST.get('key') or None
    try:
        if action == 'move':
            configs.place(config, key, x=int(float(post.get('x', 0))), y=int(float(post.get('y', 0))))
            return JsonResponse({'ok': True})
        if action == 'handle':   # a harness line pinned at (x, y), or let go (no x)
            handles = dict(configs.resolve(config)[key]['handles'])
            if post.get('x'):
                handles[post['end']] = [round(float(post['x'])), round(float(post['y']))]
            else:
                handles.pop(post.get('end'), None)
            configs.place(config, key, handles=handles)
            return JsonResponse({'ok': True})
        if action == 'place_connector':   # a connector's place on its device's outline
            side = post.get('side')
            if side not in ('top', 'right', 'bottom', 'left'):
                raise ValueError(side)
            Connector.objects.filter(pk=post.get('connector')).update(side=side, along=min(max(float(post.get('along', 0.5)), 0), 1))
            return JsonResponse({'ok': True})
        if action == 'add_device':
            device = get_object_or_404(Device, pk=post.get('device'))
            n = sum(1 for r in configs.resolve(config).values() if r['kind'] == 'device')
            same = sum(1 for r in configs.resolve(config).values() if r['device_id'] == device.pk)
            configs.place(config, kind='device', device_id=device.pk, label=post.get('label', '').strip()[:100]
                          or (f'{device.number} {same + 1}' if same else device.number),
                          x=40 + (n % 4) * GRID_X, y=40 + (n // 4) * GRID_Y)
        elif action == 'rename':
            configs.place(config, key, label=post.get('label', '').strip()[:100])
        elif action == 'swap':
            configs.place(config, key, device_id=get_object_or_404(Device, pk=post.get('device')).pk)
        elif action == 'connect':
            ends = [(post.get(side), get_object_or_404(Connector, pk=post.get(f'{side}_connector') or 0)) for side in 'ab']
            parts = []
            for side in 'ab':
                text = post.get(f'{side}_part', '').strip()
                parts.append(part_or_family(text))
                if text and parts[-1] is None:
                    raise ValidationError(f'There is no part or family "{text}".')
            harness = configs.connect(config, ends, post.get('name', ''), [json.loads(w) for w in post.getlist('wire')], parts)
            messages.success(request, f'{harness} is made, with {harness.wires.count()} wires.')
        elif action == 'request_harness':
            ask = get_user_model().objects.filter(pk=post.get('ask') or 0, is_active=True).first()
            configs.ask_harness(config, post.get('a', ''), post.get('b', ''), post.get('request', ''), ask, request.user)
            messages.success(request, f'Asked for: {ask or "the administrators"} will make it.')
        elif action in ('request_done', 'request_cancel'):
            wanted = get_object_or_404(HarnessRequest, pk=post.get('request_id'), configuration=config)
            made = Harness.objects.filter(pk=post.get('harness') or 0, project=item).first()
            configs.close_request(wanted, wanted.Status.DONE if action == 'request_done' else wanted.Status.CANCELLED, request.user, made)
        elif action == 'add_harness':
            harness = get_object_or_404(Harness, pk=post.get('harness'), project=item)
            configs.place(config, kind='harness', harness_id=harness.pk, ends=configs.plug(config, harness))
        elif action == 'plug':
            harness = get_object_or_404(Harness, pk=configs.resolve(config)[key]['harness_id'])
            wanted = {k[4:]: v for k, v in post.items() if k.startswith('end_') and v}
            configs.place(config, key, ends=configs.plug(config, harness, wanted) if wanted else {})
        elif action == 'remove':
            configs.take_away(config, key)
        elif action == 'undo':
            configs.undo(config, post.get('placement'))
        else:
            raise ValidationError('What should change?')
    except (ValidationError, KeyError, ValueError, TypeError) as exc:
        if action in ('move', 'handle', 'place_connector'):
            return JsonResponse({'ok': False}, status=400)
        errors(request, exc if isinstance(exc, ValidationError) else ValidationError('That is not in this configuration.'))
    return redirect(config.get_absolute_url())


@login_required
def needs(request, pk):
    item = get_object_or_404(Project, pk=pk)
    config = _selected(request, item)
    devices, harnesses, parts = configs.needs(config)
    count = request.GET.get('count', '')
    count = int(count) if count.isdigit() and 0 < int(count) <= 10000 else 1   # how many of it to build
    parts = [(p, q * count, have, coming, max(q * count - have - coming, 0)) for p, q, have, coming in parts]
    if request.method == 'POST':   # order what is missing
        ordered = []
        for part, _, _, _, missing in parts:
            buy = getattr(part, 'chosen', part)   # a family: the part of it ordered
            if missing and buy and buy.vendor_id:
                orders.reorder(buy, request.user, missing)
                ordered.append(buy.number)
        messages.success(request, f'On the draft orders: {", ".join(ordered)}.' if ordered else 'Nothing missing could be ordered.')
        return redirect(f'{request.path}?config={config.pk}&count={count}')
    if request.GET.get('export'):
        return excel.download(f'{item.name} {config.name}', [
            ('Parts', ['Part', 'Description', 'Needed', 'Unit', 'On hand', 'On order', 'Missing'],
             [(p.number, p.description, q, p.unit, have, coming, missing) for p, q, have, coming, missing in parts]),
            ('Devices', ['Device', 'Name', 'How many'], [(d.number, d.name, n * count) for d, n in devices]),
            ('Harnesses', ['Harness', 'Name', 'How many'], [(h.number, h.name, n * count) for h, n in harnesses])])
    return render(request, 'projects/needs.html', {'project': item, 'config': config, 'devices': devices, 'harnesses': harnesses,
                                                   'parts': parts, 'count': count})
