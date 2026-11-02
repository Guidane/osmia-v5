"""What a configuration is: its parent's devices and harnesses with its own changes (``resolve``); what those changes
are (``changes``); changing it (``place``, ``take_away``, ``undo``, ``detach``); what is wrong with it (``problems``)
and what building it needs (``needs``)."""
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Configuration, Placement

FIELDS = ('kind', 'device_id', 'label', 'x', 'y', 'harness_id', 'ends')


def _row(placement):
    return {'key': placement.key, **{f: getattr(placement, f) for f in FIELDS}}


def resolve(config):
    """{key: {kind, device_id, label, x, y, harness_id, ends, key}} of ``config``, in the order they came in."""
    out = {}
    if config is None:
        return out
    chain = config.chain()
    rows = Placement.objects.filter(configuration__in=chain)
    by_config = {}
    for p in rows:
        by_config.setdefault(p.configuration_id, []).append(p)
    for node in chain:
        for p in by_config.get(node.pk, []):
            if p.removed:
                out.pop(p.key, None)
            else:
                out[p.key] = _row(p)
    return out


def changes(config):
    """What ``config`` changes of its parent: [(placement, what, text)]; ``what`` is added, removed, changed or
    stale (a change of something its parent no longer has)."""
    from devices.models import Device
    from harnesses.models import Harness
    base = resolve(config.parent)
    devices = {d.pk: d for d in Device.objects.all()}
    harnesses = {h.pk: h for h in Harness.objects.filter(project_id=config.project_id)}
    out = []
    for p in config.placements.all():
        before = base.get(p.key)
        if p.removed:
            out.append((p, 'removed', f'{_name(before, devices, harnesses)} taken away') if before else
                       (p, 'stale', 'Something taken away that the parent no longer has'))
            continue
        thing = _name(_row(p), devices, harnesses)
        if before is None:
            out.append((p, 'added', f'{thing} added'))
        else:
            what = []
            if before['device_id'] != p.device_id:
                what.append(f'{devices.get(before["device_id"], "?")} → {devices.get(p.device_id, "?")}')
            if before['harness_id'] != p.harness_id:
                what.append(f'{harnesses.get(before["harness_id"], "?")} → {harnesses.get(p.harness_id, "?")}')
            if before['label'] != p.label:
                what.append(f'named {p.label}')
            if before['ends'] != p.ends:
                what.append('plugged in differently')
            if (before['x'], before['y']) != (p.x, p.y):
                what.append('moved')
            out.append((p, 'changed' if what else 'same', f'{thing}: {", ".join(what) or "as in its parent"}'))
    return out


def _name(row, devices, harnesses):
    if row['kind'] == 'device':
        return row['label'] or str(devices.get(row['device_id'], 'A device'))
    return str(harnesses.get(row['harness_id'], 'A harness'))


@transaction.atomic
def place(config, key=None, **fields):
    """Set what ``key`` is in ``config`` (a new key: something added): the fields given, the rest as it is now."""
    current = resolve(config).get(key) if key else None
    if key and current is None:
        raise ValidationError('That is not in this configuration.')
    values = {f: v for f, v in (current or {}).items() if f in FIELDS}
    values.update(fields)
    values.setdefault('ends', {})
    key = key or uuid.uuid4().hex[:12]
    Placement.objects.update_or_create(configuration=config, key=key, defaults={**values, 'removed': False})
    return key


@transaction.atomic
def take_away(config, key):
    """``key`` is not in ``config`` (nor in those under it, unless they add it back). Harnesses plugged into a device
    taken away come out of it."""
    rows = resolve(config)
    if key not in rows:
        raise ValidationError('That is not in this configuration.')
    if key not in resolve(config.parent):   # added here: the change goes
        Placement.objects.filter(configuration=config, key=key).delete()
    else:
        Placement.objects.update_or_create(configuration=config, key=key, defaults={'kind': rows[key]['kind'], 'removed': True})
    if rows[key]['kind'] == 'device':
        for row in rows.values():
            if row['kind'] == 'harness' and key in row['ends'].values():
                place(config, row['key'], ends={e: k for e, k in row['ends'].items() if k != key})


def undo(config, placement_id):
    """Take one of ``config``'s changes back: it is as its parent again."""
    Placement.objects.filter(configuration=config, pk=placement_id).delete()


@transaction.atomic
def detach(config):
    """``config`` becomes a setup of its own: everything it has now, no parent."""
    rows = resolve(config)
    config.placements.all().delete()
    for key, row in rows.items():
        Placement.objects.create(configuration=config, key=key, **{f: row[f] for f in FIELDS})
    config.parent = None
    config.save(update_fields=['parent'])


@transaction.atomic
def copy(config, name):
    """A new configuration at the top of the project's tree, with everything ``config`` has now."""
    new = Configuration.objects.create(project=config.project, name=name)
    for key, row in resolve(config).items():
        Placement.objects.create(configuration=new, key=key, **{f: row[f] for f in FIELDS})
    return new


def plug(config, harness, wanted=None):
    """How ``harness``'s ends plug in: ``wanted`` ({end id: device key}) where given, else the one device of the
    configuration each end's connector is on (when there is just one)."""
    rows = resolve(config)
    out = {}
    for end in harness.ends.select_related('connector'):
        chosen = (wanted or {}).get(str(end.pk))
        if chosen in rows:
            out[str(end.pk)] = chosen
        elif end.connector_id and not wanted:
            fits = [k for k, r in rows.items() if r['kind'] == 'device' and r['device_id'] == end.connector.device_id]
            if len(fits) == 1:
                out[str(end.pk)] = fits[0]
    return out


def problems(config, rows=None):
    """What is wrong with ``config``: [(key, message)]."""
    from devices.models import Device
    from harnesses.models import HarnessEnd
    rows = rows if rows is not None else resolve(config)
    devices = {d.pk: d for d in Device.objects.filter(pk__in=[r['device_id'] for r in rows.values() if r['device_id']])}
    found, taken = [], {}
    for key, row in rows.items():
        if row['kind'] != 'harness':
            continue
        for end in HarnessEnd.objects.filter(harness_id=row['harness_id']).select_related('connector__device', 'harness'):
            where = row['ends'].get(str(end.pk))
            label = f'{end.harness.number} {end.designator}'
            if where is None or where not in rows:
                found.append((key, f'{label} is not plugged in.'))
                continue
            target = rows[where]
            if end.connector is None:
                found.append((key, f'{label} has no device connector to plug into.'))
            elif end.connector.device_id != target['device_id']:
                found.append((key, f'{label} is for {end.connector.device.number} {end.connector.designator}, '
                                   f'but {target["label"] or devices.get(target["device_id"])} is a {devices.get(target["device_id"])}.'))
            else:
                spot = (where, end.connector_id)
                if spot in taken:
                    found.append((key, f'{label} and {taken[spot]} both plug into '
                                       f'{target["label"] or devices[target["device_id"]].number} {end.connector.designator}.'))
                taken[spot] = label
    return found


def needs(config):
    """What building ``config`` once takes: (devices [(device, count)], harnesses [(harness, count)],
    parts [(part, needed, on hand, on order)])."""
    from devices.models import Device
    from harnesses.models import Harness
    from orders.service import on_order
    rows = resolve(config).values()
    device_count, harness_count = {}, {}
    for row in rows:
        if row['kind'] == 'device' and row['device_id']:
            device_count[row['device_id']] = device_count.get(row['device_id'], 0) + 1
        elif row['kind'] == 'harness' and row['harness_id']:
            harness_count[row['harness_id']] = harness_count.get(row['harness_id'], 0) + 1
    devices = [(d, device_count[d.pk]) for d in Device.objects.filter(pk__in=device_count).select_related('part')]
    harnesses = [(h, harness_count[h.pk]) for h in Harness.objects.filter(pk__in=harness_count)]
    parts = {}
    for device, n in devices:
        if device.part is not None:
            parts[device.part] = parts.get(device.part, Decimal(0)) + n
    for harness, n in harnesses:
        for part, quantity in harness.parts_list():
            parts[part] = parts.get(part, Decimal(0)) + quantity * n
    return devices, harnesses, [(part, quantity, part.on_hand, on_order(part))
                                for part, quantity in sorted(parts.items(), key=lambda pq: pq[0].number)]
