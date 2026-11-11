"""Harnesses: the list, a harness's page (ends, pinout, items, parts list, what is wrong, versions, the harnesses
built: assets, each with a checklist), editing its ends, pinout and items as tables."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from devices.models import SET_TYPES as PIN_SET_TYPES, Connector
from inventory import stock
from inventory.faces import drawn, face_of
from inventory.models import Location, Part, PartGroup, choices_of_parts, part_or_family
from projects.models import Project
from assets.service import next_tag
from web import excel, rows, versions
from web.shortcuts import edit_page, errors
from web.templatetags.osmia import qty

from . import purposes
from web.forms import initial_for

from .models import COLOURS, SET_TYPES, Harness, HarnessEnd, HarnessItem, HarnessVersion, Wire, parts_of


class HarnessForm(forms.ModelForm):
    class Meta:
        model = Harness
        fields = ['project', 'name', 'description', 'status', 'notes']
        widgets = {'description': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 3})}



@login_required
def harness_list(request):
    """The harnesses, like the parts: the projects and their wire diagrams as a tree on the left, the harnesses of the
    one picked in the middle (found by number or name, by status), the details of the harness picked on the right."""
    from django.db.models import Count, Q

    from work.models import Project as Work
    found = Harness.objects.select_related('project').annotate(n_wires=Count('wires', distinct=True), n_ends=Count('ends', distinct=True))
    q = request.GET.get('q', '').strip()
    if q:
        found = found.filter(Q(number__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q))
    status = request.GET.get('status', '')
    if status in Harness.Status.values:
        found = found.filter(status=status)
    project = Project.objects.filter(pk=request.GET.get('project') or 0).first()
    work = Work.objects.filter(pk=request.GET.get('work') or 0).first() if not project else None
    if project:
        found = found.filter(project=project)
    elif work:
        found = found.filter(project__in_project=work)
    counts = dict(Harness.objects.values('project').annotate(n=Count('pk')).values_list('project', 'n'))
    diagrams = list(Project.objects.select_related('in_project').order_by('name'))
    tree = []   # (kind, thing, depth, count): a project, then its wire diagrams; wire diagrams in no project after
    for w in Work.objects.filter(wire_diagrams__isnull=False).distinct().order_by('code', 'name'):
        mine = [d for d in diagrams if d.in_project_id == w.pk]
        tree.append(('work', w, 0, sum(counts.get(d.pk, 0) for d in mine)))
        tree += [('diagram', d, 1, counts.get(d.pk, 0)) for d in mine]
    tree += [('diagram', d, 0, counts.get(d.pk, 0)) for d in diagrams if d.in_project_id is None]
    picked = Harness.objects.filter(pk=request.GET.get('harness') or 0).first()
    return render(request, 'harnesses/list.html', {
        'harnesses': found, 'project': project, 'work': work, 'tree': tree, 'q': q, 'status': status,
        'statuses': Harness.Status.choices, 'every': Harness.objects.count(), 'picked': picked,
        'brief': _brief(picked) if picked else None})


def _brief(harness):
    """What the details beside the harness list show of ``harness``."""
    wires = harness.ordered_wires()
    return {'harness': harness, 'ends': harness.ends.select_related('part', 'family', 'branch'),
            'wires': wires, 'parts': harness.parts_list(), 'problems': [text for _, text in harness.problems()]}


@login_required
def harness_brief(request, pk):
    """The details of a harness beside the harness list (fetched when one is picked)."""
    return render(request, 'harnesses/_brief.html', _brief(get_object_or_404(Harness.objects.select_related('project'), pk=pk)))


@login_required
def harness_form(request, pk=None):
    item = get_object_or_404(Harness, pk=pk) if pk else None
    return edit_page(request, HarnessForm(request.POST or None, instance=item, initial=initial_for(item, project=request.GET.get('project'))),
                     'harness')


def _sheets(harness):
    wires = harness.ordered_wires()
    return [('Pinout', ['From', 'Pin', 'To', 'Pin', 'Signal', 'Set', 'Set type', 'Colour', 'Gauge', 'Length (mm)', 'Wire part'],
             [(w.from_end.designator, w.from_pin, w.to_end.designator, w.to_pin, w.signal, w.wire_set, w.set_type, w.colour,
               w.gauge, w.length, w.used_name) for w in wires]),
            ('Connectors', ['Connector', 'Part'],
             [(e.designator, e.used_name) for e in harness.ends.select_related('part', 'family')]),
            ('Parts list', ['Part', 'Description', 'Quantity', 'Unit'],
             [(p.number, p.description, q, p.unit) for p, q in harness.parts_list()])]


@login_required
def harness(request, pk):
    item = get_object_or_404(Harness.objects.select_related('project'), pk=pk)
    if request.GET.get('export'):
        return excel.download(f'{item.number} {item.name}', _sheets(item))
    wires = item.ordered_wires()
    groups = []
    for w in wires:
        between = f'{w.from_end.designator} → {w.to_end.designator}'
        if not groups or groups[-1][0] != between:
            groups.append((between, []))
        groups[-1][1].append(w)
    found = item.problems()
    from inventory import picker
    return render(request, 'harnesses/harness.html', {'drawing': _drawing(item, wires), 'family_picker': picker.dialog(),
        'harness': item, 'ends': item.ends.select_related('part', 'family', 'branch'), 'groups': groups, 'wire_count': len(wires),
        'items': item.items.select_related('part'), 'parts': item.parts_list(),
        'problems': [text for _, text in found], 'bad_wires': {thing.pk for thing, _ in found if isinstance(thing, Wire)},
        'versions': item.versions.select_related('created_by'), 'changed': versions.changed(item),
        'units': item.assets.all(), 'locations': Location.ordered(), 'next_serial': next_tag(item.number)})


def _picked_as(found):
    """What the family popup shows as picked for an end: its family or gender (a part: the gender or family it is in)."""
    if found is None:
        return ''
    if isinstance(found, Part):
        return (found.branch or found.family or found).number
    return found.number


def _drawing(harness, wires):
    """What the pinout drawing draws: each end (the pins its wires use, in the layout of its part or family) and the
    wires between their contact numbers. (What it plugs into is its wire diagram's to say.)"""
    from devices.models import pin_order
    ends = harness.ends.select_related('part__family', 'family', 'branch__family')
    out = []
    for end in ends:
        pins = {}
        for w in wires:
            for at, pin in ((w.from_end_id, w.from_pin), (w.to_end_id, w.to_pin)):
                if at == end.pk and pin:   # (a shield joined on one side only has no pin on the other)
                    pins.setdefault(pin, '')
        numbers = sorted(pins, key=pin_order)
        out.append({'id': end.pk, 'designator': end.designator, 'what': end.used_name,
                    'side': end.side, 'used': _picked_as(end.used), 'face': drawn(end.used, numbers), 'pins': [[n, pins[n]] for n in numbers]})
    return {'colours': COLOURS, 'set_types': PIN_SET_TYPES, 'purposes': purposes.tree(), 'ends': out, 'wires': [{'id': w.pk, 'from': w.from_end_id, 'from_pin': w.from_pin, 'to': w.to_end_id, 'to_pin': w.to_pin, 'signal': w.signal,
                                    'to_signal': w.to_signal, 'set': w.wire_set, 'type': w.set_type, 'colour': w.colour, 'gauge': w.gauge, 'length': qty(w.length)} for w in wires]}


@login_required
@require_POST
def pinout_draw(request, pk):
    """The pinout edited in its drawing: a wire added between two pins (its signal and set from the device's pin), a
    wire put in a set (an existing one, a new one, or as a shielded set's shield), a set's type changed (all its
    wires; or a wire made its shield), coloured, labelled, its gauge given, or taken away; connectors added on a side, changed, taken away.
    Answers with the drawing as it is now."""
    item = get_object_or_404(Harness, pk=pk)
    post, action = request.POST, request.POST.get('action')
    if action in ('end_add', 'end_set', 'end_delete'):   # a connector added on a side, its family changed, taken away
        from inventory.picker import with_gender
        found = part_or_family(with_gender(post.get('used'))) if post.get('used') else None
        if action != 'end_delete' and post.get('used') and found is None:
            return JsonResponse({'error': f'There is no family "{post.get("used")}".'}, status=400)
        if action == 'end_add':
            taken, n = {d.upper() for d in item.ends.values_list('designator', flat=True)}, 1
            while f'P{n}' in taken:
                n += 1
            end = HarnessEnd(harness=item, designator=f'P{n}', side=post.get('side') if post.get('side') in ('left', 'right') else '',
                             position=(item.ends.aggregate(n=Max('position'))['n'] or 0) + 1)
            end.used = found
            end.save()
        else:
            end = get_object_or_404(HarnessEnd, pk=post.get('end') or 0, harness=item)
            if action == 'end_delete':
                end.delete()   # with its wires
            else:
                end.used = found
                end.save()
        return JsonResponse(_drawing(item, item.ordered_wires()))
    if action == 'shield':   # a shielded set's shield wire joined to a contact on each side ('' on a side: not there)
        name = post.get('set', '').strip()[:20]
        a = item.ends.filter(pk=post.get('a_end') or 0).first()
        b = item.ends.filter(pk=post.get('b_end') or 0).first()
        if not (name and a and b and item.wires.filter(wire_set=name).exists()):
            return JsonResponse({'error': "A set's shield goes from one of its ends to the other."}, status=400)
        a_pin, b_pin = post.get('a_pin', '').strip()[:20], post.get('b_pin', '').strip()[:20]
        shield = item.wires.filter(wire_set=name, set_type='Shield').first()
        if not (a_pin or b_pin):
            if shield:
                shield.delete()
        else:
            shield = shield or Wire(harness=item, wire_set=name, set_type='Shield', signal='Shield', colour='grey')
            shield.from_end, shield.from_pin, shield.to_end, shield.to_pin = a, a_pin, b, b_pin
            shield.save()
        return JsonResponse(_drawing(item, item.ordered_wires()))
    if action == 'add':
        a = item.ends.filter(pk=post.get('from_end') or 0).first()
        b = item.ends.filter(pk=post.get('to_end') or 0).first()
        from_pin, to_pin = post.get('from_pin', '').strip()[:20], post.get('to_pin', '').strip()[:20]
        if not (a and b and from_pin and to_pin):
            return JsonResponse({'error': "A wire goes from a connector's pin to a connector's pin."}, status=400)
        if a == b and from_pin.lower() == to_pin.lower():
            return JsonResponse({'error': 'A loopback goes to another pin.'}, status=400)
        Wire.objects.create(harness=item, from_end=a, from_pin=from_pin, to_end=b, to_pin=to_pin)
    else:
        wire = get_object_or_404(Wire, pk=post.get('wire') or 0, harness=item)
        if action == 'delete':
            wire.delete()
        elif action == 'colour':
            wire.colour = post.get('colour') if post.get('colour') in COLOURS else ''
            wire.save()
        elif action == 'signal':   # what it is for: PWR, GND, TX+, …; a loopback's other end its own (TX: RX)
            value = ' '.join(post.get('signal', '').split())[:100]
            if post.get('end') == 'to':
                wire.to_signal = value
            else:
                if wire.from_end_id == wire.to_end_id and wire.to_signal in ('', purposes.mate(wire.signal)):
                    wire.to_signal = purposes.mate(value)
                wire.signal = value
            wire.save()
        elif action == 'gauge':   # a bare number is taken as AWG
            value = ' '.join(post.get('gauge', '').split())
            wire.gauge = (f'{value} AWG' if value.isdigit() else value)[:20]
            wire.save()
        elif action == 'set':
            value = post.get('set', '').strip()
            if value.startswith('new:'):
                taken, n = set(item.wires.values_list('wire_set', flat=True)), 1
                while str(n) in taken:
                    n += 1
                kind = value[4:]
                wire.wire_set, wire.set_type = str(n), kind if kind in PIN_SET_TYPES else 'Straight'
            elif value.startswith('shield:'):
                wire.wire_set, wire.set_type = value[7:][:20], 'Shield'
            elif wire.wire_set == value:
                pass
            elif value:
                mate = item.wires.filter(wire_set=value).exclude(pk=wire.pk).exclude(set_type='Shield').first()
                wire.wire_set, wire.set_type = value[:20], mate.set_type if mate else 'Straight'
            else:
                wire.wire_set, wire.set_type = '', 'Straight'
            wire.save()
        elif action == 'set_type':   # the whole set goes together so now; or this wire is the set's shield
            kind = post.get('type', '')
            if not wire.wire_set or kind not in SET_TYPES:
                return JsonResponse({'error': 'A wire in a set, and a set type.'}, status=400)
            if kind == 'Shield':
                wire.set_type = 'Shield'
                wire.save()
            else:
                Wire.objects.filter(pk=wire.pk).update(set_type=kind)
                item.wires.filter(wire_set=wire.wire_set).exclude(set_type='Shield').update(set_type=kind)
        else:
            return JsonResponse({'error': 'Nothing to do.'}, status=400)
    return JsonResponse(_drawing(item, item.ordered_wires()))


# -- Editing as tables -------------------------------------------------------------------------------

def _part(number, row):
    """The part (or family) a row names."""
    if not number:
        return None
    part = part_or_family(number)
    if part is None:
        raise ValidationError(f'Row {row}: there is no part or family "{number}".')
    return part


def _number(text, row, what):
    if not text:
        return None
    try:
        value = Decimal(text.replace(',', '.'))
    except InvalidOperation:
        raise ValidationError(f'Row {row}: the {what} "{text}" is not a number.')
    if not value.is_finite() or value < 0:
        raise ValidationError(f'Row {row}: the {what} can\'t be below zero.')
    return value


def _edit(request, harness, title, columns, records, values, apply):
    """A page editing ``records`` of ``harness`` as a table: ``apply(row, record or None, values)`` saves one row."""
    if request.method == 'POST':
        try:
            with transaction.atomic():
                for row, record_id, gone, cells in rows.read(request.POST, columns):
                    record = next((r for r in records if r.pk == record_id), None) if record_id else None
                    if record_id and record is None:
                        continue
                    if gone:
                        record.delete()
                    else:
                        apply(row, record, cells)
        except ValidationError as exc:
            errors(request, exc)
            return redirect(request.path)
        messages.success(request, f'{title} of {harness.number} is saved.')
        return redirect(harness)
    return render(request, 'harnesses/edit.html', {
        'harness': harness, 'title': title, 'columns': columns, 'rows': rows.rows(records, values, blank=5),
        'part_numbers': choices_of_parts()})


@login_required
def ends(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    columns = [rows.Column('designator', 'Connector', width='80px'), rows.Column('part', 'Connector part or family', datalist='parts', width='220px')]
    records = list(item.ends.select_related('part', 'family'))

    def apply(row, end, cells):
        if not cells['designator']:
            raise ValidationError(f'Row {row}: give the connector a name, e.g. P1.')
        clash = item.ends.filter(designator__iexact=cells['designator']).exclude(pk=getattr(end, 'pk', None))
        if clash.exists():
            raise ValidationError(f'Row {row}: there is already a connector {cells["designator"]}.')
        end = end or HarnessEnd(harness=item, position=item.ends.count())
        end.designator, end.used = cells['designator'][:30], _part(cells['part'], row)
        end.save()
    return _edit(request, item, 'The connectors', columns, records,
                 lambda e: {'designator': e.designator, 'part': e.used_name}, apply)


@login_required
def pinout(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    end_list = list(item.ends.all())
    if not end_list:
        messages.error(request, 'Give the harness its ends first.')
        return redirect('harnesses:ends', pk)
    choices = [(e.pk, e.designator) for e in end_list]
    columns = [rows.Column('from_end', 'From', 'select', choices), rows.Column('from_pin', 'Pin', width='60px'),
               rows.Column('to_end', 'To', 'select', choices), rows.Column('to_pin', 'Pin', width='60px'),
               rows.Column('signal', 'Signal', width='120px'), rows.Column('wire_set', 'Set', width='60px'),
               rows.Column('set_type', 'Set type', 'select', [(t, t) for t in SET_TYPES]),
               rows.Column('colour', 'Colour', 'select', [(c, c) for c in COLOURS]), rows.Column('gauge', 'Gauge', width='80px'),
               rows.Column('length', 'Length (mm)', 'number', width='80px'), rows.Column('part', 'Wire part or family', datalist='parts', width='160px')]
    ends_by_id = {e.pk: e for e in end_list}
    records = item.ordered_wires()

    def apply(row, wire, cells):
        a, b = ends_by_id.get(int(cells['from_end'] or 0)), ends_by_id.get(int(cells['to_end'] or 0))
        if a is None or b is None or not cells['from_pin'] or not cells['to_pin']:
            raise ValidationError(f'Row {row}: a wire goes from a connector\'s pin to a connector\'s pin.')
        signal, wire_set = cells['signal'], cells['wire_set']
        set_type = cells['set_type'] if cells['set_type'] in SET_TYPES else 'Straight'
        wire = wire or Wire(harness=item)
        wire.from_end, wire.from_pin, wire.to_end, wire.to_pin = a, cells['from_pin'][:20], b, cells['to_pin'][:20]
        wire.signal, wire.wire_set, wire.gauge, wire.set_type = signal[:100], wire_set[:20], cells['gauge'][:20], set_type
        wire.colour = cells['colour'] if cells['colour'] in COLOURS else ''
        wire.length, wire.used = _number(cells['length'], row, 'length'), _part(cells['part'], row)
        wire.save()
    return _edit(request, item, 'The pinout', columns, records, lambda w: {
        'from_end': w.from_end_id, 'from_pin': w.from_pin, 'to_end': w.to_end_id, 'to_pin': w.to_pin, 'signal': w.signal,
        'wire_set': w.wire_set, 'set_type': w.set_type, 'colour': w.colour, 'gauge': w.gauge,
        'length': f'{w.length.normalize():f}' if w.length is not None else '', 'part': w.used_name}, apply)


@login_required
def items(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    columns = [rows.Column('part', 'Part or family', datalist='parts', width='180px'), rows.Column('quantity', 'Quantity', 'number', width='90px'),
               rows.Column('note', 'Note', width='240px')]

    def apply(row, line, cells):
        quantity = _number(cells['quantity'], row, 'quantity')
        part = _part(cells['part'], row)
        if part is None or not quantity:
            raise ValidationError(f'Row {row}: give the part and how many.')
        line = line or HarnessItem(harness=item)
        line.used, line.quantity, line.note = part, quantity, cells['note'][:200]
        line.save()
    return _edit(request, item, 'The other items', columns, list(item.items.select_related('part', 'family')),
                 lambda i: {'part': i.used_name, 'quantity': f'{i.quantity.normalize():f}', 'note': i.note}, apply)


# -- Versions ------------------------------------------------------------------------------------------

@login_required
@require_POST
def save_version(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    try:
        version = versions.save(item, request.user, request.POST.get('note', ''))
        messages.success(request, f'{item.number} is saved as v{version.number}.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)


@login_required
def version(request, pk, number):
    item = get_object_or_404(Harness, pk=pk)
    saved = get_object_or_404(HarnessVersion, harness=item, number=number)
    return render(request, 'harnesses/version.html', {'harness': item, 'version': saved, 'data': saved.data, 'parts': parts_of(saved.data)})


@login_required
@require_POST
def restore(request, pk, number):
    item = get_object_or_404(Harness, pk=pk)
    versions.restore(item, get_object_or_404(HarnessVersion, harness=item, number=number))
    messages.success(request, f'{item.number} is as it was in v{number}: save a version to keep it.')
    return redirect(item)


# -- Harnesses built: each an asset -------------------------------------------------------------------

@transaction.atomic
def build(harness, number, version, user, take_from=None):
    """A harness built: an asset (asset tag ``number``) of the version it is built to (else as it is now), being built,
    with a checklist of its wires; its parts taken out of ``take_from`` when given."""
    from assets.models import Asset, AssetCheck
    from assets.service import event
    number = (number or '').strip()
    if not number:
        raise ValidationError('Give it an asset tag.')
    if Asset.objects.filter(number__iexact=number).exists():
        raise ValidationError(f'There is already an asset {number}.')
    data = version.data if version else harness.snapshot()
    if not data.get('wires'):
        raise ValidationError(f'{harness.number} has no pinout yet.')
    asset = Asset.objects.create(number=number[:100], name=harness.name, kind=Asset.Kind.HARNESS, harness=harness,
                                 version=version.number if version else None, status=Asset.Status.BUILDING,
                                 built_by=user, built_on=date.today())
    AssetCheck.objects.bulk_create(AssetCheck(
        asset=asset, position=i, wire=f'{w["from"]}:{w["from_pin"]} → {w["to"]}:{w["to_pin"]}', between=f'{w["from"]} → {w["to"]}',
        signal=w.get('signal', ''), colour=w.get('colour', ''), wire_set=w.get('set', '')) for i, w in enumerate(data['wires']))
    if take_from is not None:
        for part, quantity in parts_of(data):
            take = stock.use_any if isinstance(part, PartGroup) else stock.use
            take(part, quantity, take_from, user, note=f'built into {asset.number}')
    event(asset, 'built', user, f'{harness.number}' + (f' v{version.number}' if version else ''))
    return asset


@login_required
@require_POST
def unit_add(request, pk):
    item = get_object_or_404(Harness, pk=pk)
    version_pk = request.POST.get('version')
    chosen = item.versions.filter(pk=version_pk).first() if version_pk else None
    where = Location.objects.filter(pk=request.POST.get('take_from') or 0).first()
    try:
        asset = build(item, request.POST.get('serial'), chosen, request.user, where)
    except ValidationError as exc:
        errors(request, exc)
        return redirect(item)
    return redirect(asset)
