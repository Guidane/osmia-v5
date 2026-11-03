"""Devices: designs made in-house (a controller, a load board) or bought (a power supply, a meter), with their
connectors and each connector's pins and signals, saved as versions. Each one built or bought is an asset (``assets``)
linked to its design."""
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse

from inventory.models import Part
from web.models import Version

COLOURS = ['#3b7dd8', '#2e7d5b', '#c2410c', '#7c3aed', '#be185d', '#0891b2', '#a16207', '#4b5563']


def pin_order(number):
    """Pins in natural order: 2 before 10, A2 before A10."""
    import re
    return [(0, int(p), '') if p.isdigit() else (1, 0, p.lower()) for p in re.split(r'(\d+)', number or '') if p]


class Device(models.Model):
    class Origin(models.TextChoices):
        IN_HOUSE = 'in_house', 'Made in-house'
        EXTERNAL = 'external', 'Bought (external)'

    number = models.CharField('device number', max_length=100)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    origin = models.CharField(max_length=10, choices=Origin, default=Origin.IN_HOUSE)
    manufacturer = models.CharField(max_length=200, blank=True)
    model = models.CharField(max_length=200, blank=True)
    part = models.ForeignKey(Part, null=True, blank=True, on_delete=models.SET_NULL, related_name='devices')
    colour = models.CharField(max_length=7, default=COLOURS[0])
    notes = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=0, editable=False)   # the last version saved
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']
        constraints = [models.UniqueConstraint(Lower('number'), name='unique_device_number',
                                               violation_error_message='There is already a device with this number.')]

    def __str__(self):
        return f'{self.number} {self.name}'

    def get_absolute_url(self):
        return reverse('devices:device', args=[self.pk])

    def snapshot(self):
        return {'number': self.number, 'name': self.name, 'description': self.description, 'manufacturer': self.manufacturer,
                'model': self.model, 'part': self.part.number if self.part else '', 'notes': self.notes,
                'connectors': [c.snapshot() for c in self.connectors.prefetch_related('pins').select_related('part')]}

    def restore(self, data):
        """As it was in ``data``: its fields, and its connectors and pins matched by designator and number (what
        harnesses plug into keeps its connector)."""
        for key in ('number', 'name', 'description', 'manufacturer', 'model', 'notes'):
            setattr(self, key, data.get(key, ''))
        self.part = Part.objects.filter(number=data.get('part') or '').first()
        self.save()
        wanted = {c['designator']: c for c in data.get('connectors', [])}
        for connector in self.connectors.all():
            if connector.designator not in wanted:
                connector.delete()
        for position, (designator, c) in enumerate(wanted.items()):
            connector, _ = Connector.objects.update_or_create(device=self, designator=designator, defaults={
                'name': c.get('name', ''), 'part': Part.objects.filter(number=c.get('part') or '').first(), 'position': position})
            pins = {p['number']: p for p in c.get('pins', [])}
            connector.pins.exclude(number__in=pins).delete()
            for number, p in pins.items():
                Pin.objects.update_or_create(connector=connector, number=number,
                                             defaults={'signal': p.get('signal', ''), 'description': p.get('description', '')})


class Connector(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='connectors')
    designator = models.CharField(max_length=30)
    name = models.CharField(max_length=200, blank=True)
    part = models.ForeignKey(Part, null=True, blank=True, on_delete=models.SET_NULL, related_name='device_connectors')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'designator']
        constraints = [models.UniqueConstraint(fields=['device', 'designator'], name='unique_connector_designator')]

    def __str__(self):
        return f'{self.device.number} {self.designator}'

    def snapshot(self):
        return {'designator': self.designator, 'name': self.name, 'part': self.part.number if self.part else '',
                'pins': [{'number': p.number, 'signal': p.signal, 'description': p.description} for p in self.ordered_pins()]}

    def ordered_pins(self):
        return sorted(self.pins.all(), key=lambda p: pin_order(p.number))


class Pin(models.Model):
    connector = models.ForeignKey(Connector, on_delete=models.CASCADE, related_name='pins')
    number = models.CharField(max_length=20)
    signal = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['connector', 'number'], name='unique_pin_number')]

    def __str__(self):
        return f'{self.connector}:{self.number}'


class DeviceVersion(Version):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='versions')

    class Meta(Version.Meta):
        constraints = [models.UniqueConstraint(fields=['device', 'number'], name='unique_device_version')]
