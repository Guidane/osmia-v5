"""Devices: the list, a device's page (its connectors and pins, versions, the assets that are it and the harnesses
plugged into it), and changing them."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inventory.faces import drawn
from web import excel, versions
from web.shortcuts import edit_page, errors

from .forms import ConnectorForm, DeviceForm
from .models import SET_TYPES, Connector, Device, DeviceVersion, Pin, pin_order



@login_required
def device_list(request):
    q = request.GET.get('q', '').strip()
    found = Device.objects.annotate(n_connectors=Count('connectors', distinct=True), n_units=Count('assets', distinct=True))
    if q:
        found = found.filter(Q(number__icontains=q) | Q(name__icontains=q) | Q(manufacturer__icontains=q) | Q(model__icontains=q))
    origin = request.GET.get('origin', '')
    if origin in Device.Origin.values:
        found = found.filter(origin=origin)
    if request.GET.get('export'):
        return excel.download('devices', [('Devices', ['Number', 'Name', 'Origin', 'Manufacturer', 'Model', 'Version', 'Connectors', 'Units'],
                                           [(d.number, d.name, d.get_origin_display(), d.manufacturer, d.model, d.version, d.n_connectors,
                                             d.n_units) for d in found]),
                                          ('Pins', PIN_HEAD, _pin_rows(found))])
    return render(request, 'devices/list.html', {'devices': found, 'q': q, 'origin': origin, 'origins': Device.Origin.choices})


PIN_HEAD = ['Device', 'Connector', 'Connector name', 'Connector part', 'Pin', 'Signal', 'Set', 'Set type', 'Description']


def _pin_rows(devices):
    for device in devices:
        for connector in device.connectors.select_related('part', 'family').prefetch_related('pins'):
            for pin in connector.ordered_pins():
                yield (device.number, connector.designator, connector.name, connector.used_name,
                       pin.number, pin.signal, pin.wire_set, pin.set_type if pin.wire_set else '', pin.description)


@login_required
def device_form(request, pk=None):
    item = get_object_or_404(Device, pk=pk) if pk else None
    form = DeviceForm(request.POST or None, instance=item)
    with transaction.atomic():
        return edit_page(request, form, 'device', saved=lambda device, new: form.add_unit(device))


@login_required
@require_POST
def device_delete(request, pk):
    """The device, with its connectors and versions; its assets stay, no longer of a device. Not while a wire diagram
    has it."""
    item = get_object_or_404(Device, pk=pk)
    diagrams = sorted({str(p.configuration.project) for p in item.placements.filter(removed=False)
                       .select_related('configuration__project')})
    if diagrams:
        messages.error(request, f'{item} is in the wire diagram {", ".join(diagrams)}: take it out there first.')
        return redirect('devices:list')
    with transaction.atomic():
        item.assets.update(device=None)
        item.placements.all().delete()   # only where a configuration had taken it out
        item.delete()
    messages.success(request, f'{item} is deleted.')
    return redirect('devices:list')


@login_required
def device(request, pk):
    from harnesses.models import HarnessEnd
    item = get_object_or_404(Device.objects.select_related('part', 'family'), pk=pk)
    if request.GET.get('export'):
        return excel.download(item.number, [('Pins', PIN_HEAD, _pin_rows([item]))])
    connectors = list(item.connectors.select_related('part', 'family').prefetch_related('pins'))
    from projects.configs import spot
    from projects.models import Placement
    plugged, mine = {}, {c.pk for c in connectors}   # the harness ends the wire diagrams plug into its connectors
    for p in Placement.objects.filter(kind='harness', removed=False).exclude(harness=None):
        for end_id, value in (p.ends or {}).items():
            connector_id = spot(value)[1]
            if connector_id in mine:
                plugged.setdefault(connector_id, set()).add(int(end_id))
    ends = {e.pk: e for e in HarnessEnd.objects.filter(pk__in={e for found in plugged.values() for e in found}).select_related('harness__project')}
    plugged = {c: sorted((ends[e] for e in found if e in ends), key=lambda e: (e.harness.number, e.designator)) for c, found in plugged.items()}
    faces = {}
    for c in connectors:
        pins = c.ordered_pins()
        faces[c.pk] = {'face': drawn(c.used, [p.number for p in pins]), 'pins': [[p.number, p.signal] for p in pins]}
    return render(request, 'devices/device.html', {
        'device': item, 'connectors': [(c, c.ordered_pins(), plugged.get(c.pk, [])) for c in connectors], 'faces': faces,
        'versions': item.versions.select_related('created_by'), 'changed': versions.changed(item),
        'units': item.assets.select_related('location')})


@login_required
def connector_form(request, pk, connector=None):
    item = get_object_or_404(Device, pk=pk)
    current = get_object_or_404(Connector, pk=connector, device=item) if connector else Connector(device=item)
    form = ConnectorForm(request.POST or None, instance=current)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            saved = form.save(commit=False)
            if not saved.pk:
                saved.position = item.connectors.count()
            saved.save()
            Pin.objects.bulk_create(Pin(connector=saved, number=n) for n in form.cleaned_data.get('pins') or [])
        return redirect(f'{item.get_absolute_url()}#c{saved.pk}')
    return render(request, 'web/form.html', {'form': form, 'back': item.get_absolute_url(),
                                                   'title': f'Change {current}' if current.pk else f'New connector on {item}'})


def free_designator(device, wanted):
    """``wanted`` if the device has no connector of that name yet, else the next free one (J1 taken: J2, J3, …)."""
    import re
    taken = {d.lower() for d in device.connectors.values_list('designator', flat=True)}
    if wanted.lower() not in taken:
        return wanted
    stem, number = re.match(r'^(.*?)(\d*)$', wanted).groups()
    n = int(number or 1) + 1
    while f'{stem}{n}'.lower() in taken:
        n += 1
    return f'{stem}{n}'[:30]


@login_required
def connectors_copy(request, pk):
    """Connectors of other devices, picked from a tree (device, then its connectors), copied here with their pins."""
    item = get_object_or_404(Device, pk=pk)
    if request.method == 'POST':
        copied = []
        with transaction.atomic():
            for source in Connector.objects.filter(pk__in=request.POST.getlist('connector')).exclude(device=item).prefetch_related('pins'):
                made = Connector.objects.create(device=item, designator=free_designator(item, source.designator), name=source.name,
                                                part=source.part, family=source.family, branch=source.branch, position=item.connectors.count())
                Pin.objects.bulk_create(Pin(connector=made, number=p.number, signal=p.signal, wire_set=p.wire_set, set_type=p.set_type,
                                            description=p.description) for p in source.pins.all())
                copied.append(made.designator if made.designator == source.designator else f'{source.designator} (as {made.designator})')
        messages.success(request, f'Copied: {", ".join(copied)}.' if copied else 'Nothing was picked.')
        return redirect(item)
    others = Device.objects.exclude(pk=item.pk).filter(connectors__isnull=False).distinct().prefetch_related(
        'connectors__pins', 'connectors__part', 'connectors__family', 'connectors__branch')
    return render(request, 'devices/copy.html', {'device': item, 'others': others})


@login_required
@require_POST
def connector_delete(request, pk, connector):
    item = get_object_or_404(Connector, pk=connector, device_id=pk)
    item.delete()
    messages.success(request, f'{item.designator} is taken away.')
    return redirect('devices:device', pk)


@login_required
def pins(request, pk, connector):
    """A connector's pins as one form: numbers, signals, sets (from a list, or a new one), descriptions; new rows add
    pins, ✕ takes one away. The pins of a set are all of one type: the one changed, else the one it had."""
    item = get_object_or_404(Connector.objects.select_related('device'), pk=connector, device_id=pk)
    rows = item.ordered_pins()
    if request.method == 'POST':
        try:
            with transaction.atomic():
                post = request.POST
                had = {p.wire_set: p.set_type for p in rows if p.wire_set}   # each set's type before
                typed = {}                                                   # each set's type, where it was changed
                for pin in rows:
                    if post.get(f'gone_{pin.pk}'):
                        pin.delete()
                        continue
                    before = pin.set_type
                    pin.number = post.get(f'number_{pin.pk}', pin.number).strip() or pin.number
                    pin.signal = post.get(f'signal_{pin.pk}', '').strip()[:100]
                    pin.wire_set, pin.set_type = _set(post, pin.pk)
                    pin.description = post.get(f'description_{pin.pk}', '').strip()[:200]
                    pin.save()
                    if pin.wire_set and pin.set_type != before:
                        typed[pin.wire_set] = pin.set_type
                for i in range(int(post.get('new', 0) or 0)):
                    number = post.get(f'number_new{i}', '').strip()
                    if number:
                        wire_set, set_type = _set(post, f'new{i}')
                        Pin.objects.create(connector=item, number=number[:20], signal=post.get(f'signal_new{i}', '').strip()[:100],
                                           wire_set=wire_set, set_type=set_type, description=post.get(f'description_new{i}', '').strip()[:200])
                        if wire_set and wire_set not in had:
                            typed.setdefault(wire_set, set_type)
                for wire_set in set(item.pins.exclude(wire_set='').values_list('wire_set', flat=True)):
                    one = typed.get(wire_set) or had.get(wire_set)
                    if one:
                        item.pins.filter(wire_set=wire_set).update(set_type=one)
        except IntegrityError:
            messages.error(request, 'Two pins have the same number: nothing was saved.')
            return redirect(request.path)
        messages.success(request, f'The pins of {item} are saved.')
        return redirect(f'{item.device.get_absolute_url()}#c{item.pk}')
    return render(request, 'devices/pins.html', {'connector': item, 'pins': rows, 'new': range(5), 'set_types': SET_TYPES,
                                                 'sets': sorted({p.wire_set for p in rows if p.wire_set}, key=pin_order)})


def _set(post, row):
    """A pins form row's set and set type."""
    set_type = post.get(f'set_type_{row}', '')
    wire_set = post.get(f'set_{row}', '').strip()[:20]
    return ('' if wire_set == '+' else wire_set), set_type if set_type in SET_TYPES else 'Straight'


@login_required
@require_POST
def save_version(request, pk):
    item = get_object_or_404(Device, pk=pk)
    try:
        version = versions.save(item, request.user, request.POST.get('note', ''))
        messages.success(request, f'{item.number} is saved as v{version.number}.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)


@login_required
def version(request, pk, number):
    item = get_object_or_404(Device, pk=pk)
    saved = get_object_or_404(DeviceVersion, device=item, number=number)
    for c in saved.data.get('connectors', []):
        c['pins'] = sorted(c.get('pins', []), key=lambda p: pin_order(p['number']))
    return render(request, 'devices/version.html', {'device': item, 'version': saved, 'data': saved.data})


@login_required
@require_POST
def restore(request, pk, number):
    item = get_object_or_404(Device, pk=pk)
    saved = get_object_or_404(DeviceVersion, device=item, number=number)
    versions.restore(item, saved)
    messages.success(request, f'{item.number} is as it was in v{number}: save a version to keep it.')
    return redirect(item)
