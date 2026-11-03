"""Assets: every thing kept one by one with an asset tag — tools, lab equipment (power supplies, scopes), measuring
instruments, electronics, the devices and harnesses built or bought, IT. Its kind is picked from a list; its category (the
same tree as parts') gives it attributes, shared with the parts of that category. Where it is kept, who looks after it, who has it out now,
when it is due for calibration, everything that happened to it; what it was bought for (an order line) or built as (a
device or harness design, the version, a harness's checklist). Parts link to assets they need with a "link to an
asset" attribute (a contact's "Crimped with")."""
import calendar
from datetime import date

from django.conf import settings
from django.db import models
from django.urls import reverse

from inventory.models import Attribute, Category, Location, Part, Vendor


class Asset(models.Model):
    class Kind(models.TextChoices):
        TOOL = 'tool', 'Tool'
        LAB = 'lab', 'Lab equipment'
        MEASURING = 'measuring', 'Measuring instrument'
        ELECTRONICS = 'electronics', 'Electronics'
        DEVICE = 'device', 'Device'
        HARNESS = 'harness', 'Harness'
        IT = 'it', 'Computer / IT'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        ORDERED = 'ordered', 'On order'
        BUILDING = 'building', 'Being built'
        AVAILABLE = 'available', 'Available'
        OUT = 'out', 'Checked out'
        IN_USE = 'in_use', 'In use'
        CALIBRATION = 'calibration', 'Away for calibration'
        REPAIR = 'repair', 'In repair'
        RETIRED = 'retired', 'Retired'

    number = models.CharField('asset tag', max_length=100, unique=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=Kind, default=Kind.TOOL)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name='assets')
    manufacturer = models.CharField(max_length=200, blank=True)
    model = models.CharField(max_length=200, blank=True)
    serial = models.CharField('serial number', max_length=100, blank=True)
    device = models.ForeignKey('devices.Device', null=True, blank=True, on_delete=models.PROTECT, related_name='assets')
    harness = models.ForeignKey('harnesses.Harness', null=True, blank=True, on_delete=models.PROTECT, related_name='assets')
    version = models.PositiveIntegerField(null=True, blank=True)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL, related_name='assets')
    keeper = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='kept_assets')
    status = models.CharField(max_length=12, choices=Status, default=Status.AVAILABLE)
    holder = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='held_assets',
                               editable=False)   # who has it out
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name='assets')
    vendor_number = models.CharField("vendor's number", max_length=200, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    calibrated_on = models.DateField(null=True, blank=True)
    calibration_months = models.PositiveIntegerField('calibration every (months)', null=True, blank=True)
    built_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
                                 editable=False)
    built_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return f'{self.number} {self.name}'

    def get_absolute_url(self):
        return reverse('assets:asset', args=[self.pk])

    @property
    def description(self):   # what lists of parts and assets show next to the number
        return self.name

    @property
    def calibration_due(self):
        if not self.calibration_months:
            return None
        if self.calibrated_on is None:
            return date.today()   # never calibrated: due now
        months = self.calibrated_on.month - 1 + self.calibration_months
        year, month = self.calibrated_on.year + months // 12, months % 12 + 1
        return date(year, month, min(self.calibrated_on.day, calendar.monthrange(year, month)[1]))

    @property
    def calibration_overdue(self):
        due = self.calibration_due
        return due is not None and due <= date.today() and self.status != self.Status.RETIRED


class AssetValue(models.Model):
    """What an asset fills in for an attribute of its type (``number`` too, for numbers: to sort and filter by)."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='values')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='asset_values')
    value = models.CharField(max_length=200)
    number = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['asset', 'attribute'], name='unique_asset_value')]


class AssetLink(models.Model):
    """An asset naming a part or another asset with an "interacts with" attribute or a link (a crimp tool that crimps
    these contacts, a die that fits that tool)."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='links')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='asset_targets')
    part = models.ForeignKey(Part, null=True, blank=True, on_delete=models.CASCADE, related_name='linked_from_assets')
    target = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.CASCADE, related_name='linked_from')


class PartAsset(models.Model):
    """A part linking to an asset with a "link to an asset" attribute (a contact "Crimped with" a crimp tool)."""
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='asset_links')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='asset_links')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='part_links')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['part', 'attribute', 'asset'], name='unique_part_asset')]


class AssetCheck(models.Model):
    """A wire of a harness built: what it was when built, placed and verified."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='checks')
    wire = models.CharField(max_length=100)          # "P1:3 → P2:5"
    between = models.CharField(max_length=70)        # "P1 → P2": its heading
    signal = models.CharField(max_length=100, blank=True)
    colour = models.CharField(max_length=20, blank=True)
    wire_set = models.CharField(max_length=20, blank=True)
    placed = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position']


class AssetEvent(models.Model):
    """Something that happened to an asset: checked out or back, calibrated, sent away, received, built, a note."""
    class Kind(models.TextChoices):
        OUT = 'out', 'Checked out'
        BACK = 'back', 'Brought back'
        CALIBRATED = 'calibrated', 'Calibrated'
        AWAY = 'away', 'Sent away'
        RECEIVED = 'received', 'Received'
        BUILT = 'built', 'Built'
        NOTE = 'note', 'Note'

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=12, choices=Kind)
    note = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at', '-pk']
