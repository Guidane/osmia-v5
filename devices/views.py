"""Devices: the list, a device's page (its connectors and pins, versions, the assets that are it and the harnesses
plugged into it), and changing them."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from assets.service import next_tag
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
    return edit_page(request, DeviceForm(request.POST or None, instance=item), 'device')


@login_required
def device(request, pk):
    from harnesses.models import HarnessEnd
    item = get_object_or_404(Device.objects.select_related('part', 'family'), pk=pk)
    if request.GET.get('export'):
        return excel.download(item.number, [('Pins', PIN_HEAD, _pin_rows([item]))])
    connectors = list(item.connectors.select_related('part', 'family').prefetch_related('pins'))
    plugged = {}
    for end in HarnessEnd.objects.filter(connector__device=item).select_related('harness__project', 'connector'):
        plugged.setdefault(end.connector_id, []).append(end)
    return render(request, 'devices/device.html', {
        'device': item, 'connectors': [(c, c.ordered_pins(), plugged.get(c.pk, [])) for c in connectors],
        'versions': item.versions.select_related('created_by'), 'changed': versions.changed(item),
        'units': item.assets.select_related('location'), 'next_tag': next_tag(item.number)})


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


@login_required
@require_POST
def connector_delete(request, pk, connector):
    item = get_object_or_404(Connector, pk=connector, device_id=pk)
    item.delete()
    messages.success(request, f'{item.designator} is taken away.')
    return redirect('devices:device', pk)


@login_required
def pins(request, pk, connector):
    """A connector's pins as one form: numbers, signals, sets, descriptions; new rows add pins, ✕ takes one away."""
    item = get_object_or_404(Connector.objects.select_related('device'), pk=connector, device_id=pk)
    rows = item.ordered_pins()
    if request.method == 'POST':
        try:
            with transaction.atomic():
                post = request.POST
                for pin in rows:
                    if post.get(f'gone_{pin.pk}'):
                        pin.delete()
                        continue
                    pin.number = post.get(f'number_{pin.pk}', pin.number).strip() or pin.number
                    pin.signal = post.get(f'signal_{pin.pk}', '').strip()[:100]
                    pin.wire_set, pin.set_type = _set(post, pin.pk)
                    pin.description = post.get(f'description_{pin.pk}', '').strip()[:200]
                    pin.save()
                for i in range(int(post.get('new', 0) or 0)):
                    number = post.get(f'number_new{i}', '').strip()
                    if number:
                        wire_set, set_type = _set(post, f'new{i}')
                        Pin.objects.create(connector=item, number=number[:20], signal=post.get(f'signal_new{i}', '').strip()[:100],
                                           wire_set=wire_set, set_type=set_type, description=post.get(f'description_new{i}', '').strip()[:200])
        except IntegrityError:
            messages.error(request, 'Two pins have the same number: nothing was saved.')
            return redirect(request.path)
        messages.success(request, f'The pins of {item} are saved.')
        return redirect(f'{item.device.get_absolute_url()}#c{item.pk}')
    return render(request, 'devices/pins.html', {'connector': item, 'pins': rows, 'new': range(5), 'set_types': SET_TYPES})


def _set(post, row):
    """A pins form row's set and set type."""
    set_type = post.get(f'set_type_{row}', '')
    return post.get(f'set_{row}', '').strip()[:20], set_type if set_type in SET_TYPES else 'Straight'


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
