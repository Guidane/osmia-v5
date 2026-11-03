"""Harnesses: each belongs to a project. Its ends (each a connector, plugged into a device's connector), its pinout
(wires from an end's pin to another end's pin), extra items (contacts, ties, sleeving), saved as versions. Each one
built is an asset (``assets``) with a checklist of its wires, placed and verified."""
from collections import OrderedDict
from decimal import Decimal

from django.db import models, transaction
from django.urls import reverse

from devices.models import Connector, pin_order
from inventory.models import Part
from web.models import Version

SET_TYPES = ['Straight', 'Twisted', 'Shielded twisted', 'Shielded', 'Shield']
COLOURS = ['black', 'brown', 'red', 'orange', 'yellow', 'green', 'blue', 'violet', 'grey', 'white', 'green/yellow']


class Harness(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        RELEASED = 'released', 'Released'
        OBSOLETE = 'obsolete', 'Obsolete'

    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, related_name='harnesses')
    number = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']
        verbose_name_plural = 'harnesses'

    def __str__(self):
        return f'{self.number} {self.name}'

    def get_absolute_url(self):
        return reverse('harnesses:harness', args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.number:
            with transaction.atomic():
                last = Harness.objects.select_for_update().order_by('-pk').values_list('pk', flat=True).first() or 0
                self.number = f'H-{last + 1:04d}'
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def ordered_wires(self):
        return sorted(self.wires.select_related('from_end', 'to_end', 'part'),
                      key=lambda w: (w.from_end.designator, w.to_end.designator, pin_order(w.from_pin)))

    def parts_list(self):
        """What it is made of now: [(part, quantity)]."""
        return parts_of(self.snapshot())

    def problems(self):
        """What is wrong with its pinout: [(wire or end or None, message)]."""
        found, used = [], {}
        ends = list(self.ends.select_related('connector__device').prefetch_related('connector__pins'))
        for end in ends:
            if end.connector is None:
                found.append((end, f'{end.designator} is not plugged into a device connector.'))
        for wire in self.ordered_wires():
            for end, pin in ((wire.from_end, wire.from_pin), (wire.to_end, wire.to_pin)):
                if wire.set_type != 'Shield':   # a shield's drain may share a pin
                    used.setdefault((end.pk, pin.lower()), (f'{end.designator}:{pin}', []))[1].append(wire)
                if end.connector_id is None:
                    continue
                device_pin = end.connector.pins.filter(number__iexact=pin).first()
                if device_pin is None:
                    found.append((wire, f'{end.connector} has no pin {pin} ({wire}).'))
                elif wire.signal and device_pin.signal and wire.signal.strip().lower() != device_pin.signal.strip().lower():
                    found.append((wire, f'{wire}: the wire carries "{wire.signal}", {end.connector}:{pin} is "{device_pin.signal}".'))
        for where, wires in used.values():
            if len(wires) > 1:
                found.append((wires[1], f'{where} has {len(wires)} wires.'))
        return found

    def snapshot(self):
        return {'name': self.name, 'description': self.description, 'notes': self.notes,
                'ends': [{'designator': e.designator, 'part': e.part.number if e.part else '',
                          'connector': [e.connector.device.number, e.connector.designator] if e.connector else None}
                         for e in self.ends.select_related('part', 'connector__device')],
                'wires': [{'from': w.from_end.designator, 'from_pin': w.from_pin, 'to': w.to_end.designator, 'to_pin': w.to_pin,
                           'signal': w.signal, 'set': w.wire_set, 'set_type': w.set_type, 'colour': w.colour, 'gauge': w.gauge,
                           'length': str(w.length) if w.length is not None else None, 'part': w.part.number if w.part else ''}
                          for w in self.ordered_wires()],
                'items': [{'part': i.part.number, 'quantity': str(i.quantity), 'note': i.note} for i in self.items.select_related('part')]}

    def restore(self, data):
        def part(number):
            return Part.objects.filter(number=number or '').first()
        self.name, self.description, self.notes = data.get('name', ''), data.get('description', ''), data.get('notes', '')
        self.save()
        self.wires.all().delete()
        self.items.all().delete()
        wanted = {e['designator']: e for e in data.get('ends', [])}
        self.ends.exclude(designator__in=wanted).delete()
        ends = {}
        for position, (designator, e) in enumerate(wanted.items()):
            where = e.get('connector')
            connector = Connector.objects.filter(device__number=where[0], designator=where[1]).first() if where else None
            ends[designator], _ = HarnessEnd.objects.update_or_create(harness=self, designator=designator, defaults={
                'part': part(e.get('part')), 'connector': connector, 'position': position})
        for w in data.get('wires', []):
            Wire.objects.create(harness=self, from_end=ends[w['from']], from_pin=w['from_pin'], to_end=ends[w['to']], to_pin=w['to_pin'],
                                signal=w.get('signal', ''), wire_set=w.get('set', ''), set_type=w.get('set_type', 'Straight'),
                                colour=w.get('colour', ''), gauge=w.get('gauge', ''), part=part(w.get('part')),
                                length=Decimal(w['length']) if w.get('length') else None)
        for i in data.get('items', []):
            if part(i['part']):
                HarnessItem.objects.create(harness=self, part=part(i['part']), quantity=Decimal(i['quantity']), note=i.get('note', ''))


def parts_of(data):
    """What a harness as in ``data`` (a snapshot) is made of: [(part, quantity)], its ends' connectors, its wire (in
    metres when the wire's part is counted in metres) and its other items."""
    wanted = [(e['part'], Decimal(1), None) for e in data.get('ends', []) if e.get('part')]
    wanted += [(w['part'], None, Decimal(w['length'] or 0)) for w in data.get('wires', []) if w.get('part')]
    wanted += [(i['part'], Decimal(i['quantity']), None) for i in data.get('items', [])]
    parts = {p.number: p for p in Part.objects.filter(number__in={n for n, _, _ in wanted})}
    need = OrderedDict()
    for number, quantity, length in wanted:
        part = parts.get(number)
        if part is None:
            continue
        if quantity is None:   # a wire
            quantity = length / 1000 if part.unit == Part.Unit.M else Decimal(1)
        need[part] = need.get(part, Decimal(0)) + quantity
    return list(need.items())


class HarnessEnd(models.Model):
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='ends')
    designator = models.CharField(max_length=30)
    part = models.ForeignKey(Part, null=True, blank=True, on_delete=models.SET_NULL, related_name='harness_ends')
    connector = models.ForeignKey(Connector, null=True, blank=True, on_delete=models.SET_NULL, related_name='harness_ends')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'designator']
        constraints = [models.UniqueConstraint(fields=['harness', 'designator'], name='unique_end_designator')]

    def __str__(self):
        return self.designator


class Wire(models.Model):
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='wires')
    from_end = models.ForeignKey(HarnessEnd, on_delete=models.CASCADE, related_name='wires_from')
    from_pin = models.CharField(max_length=20)
    to_end = models.ForeignKey(HarnessEnd, on_delete=models.CASCADE, related_name='wires_to')
    to_pin = models.CharField(max_length=20)
    signal = models.CharField(max_length=100, blank=True)
    wire_set = models.CharField('set', max_length=20, blank=True)
    set_type = models.CharField(max_length=20, default='Straight', choices=[(t, t) for t in SET_TYPES])
    colour = models.CharField(max_length=20, blank=True, choices=[(c, c) for c in COLOURS])
    gauge = models.CharField(max_length=20, blank=True)
    length = models.DecimalField('length (mm)', max_digits=9, decimal_places=1, null=True, blank=True)
    part = models.ForeignKey(Part, null=True, blank=True, on_delete=models.SET_NULL, related_name='harness_wires')

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return f'{self.from_end.designator}:{self.from_pin} → {self.to_end.designator}:{self.to_pin}'


class HarnessItem(models.Model):
    """Something else it is made of: contacts, ties, sleeving, labels."""
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='items')
    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name='harness_items')
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['pk']


class HarnessVersion(Version):
    harness = models.ForeignKey(Harness, on_delete=models.CASCADE, related_name='versions')

    class Meta(Version.Meta):
        constraints = [models.UniqueConstraint(fields=['harness', 'number'], name='unique_harness_version')]
