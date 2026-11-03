"""Parts and where they are: vendors, part categories (a tree, each with attributes its parts fill in, trickling
down to the categories under it), parts with their attribute values, locations (a tree:
building → room → shelf → bin), how many of a part are in each location, and every movement of stock.

Stock only changes through ``inventory.stock``, which keeps a Movement for each change.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Lower
from django.urls import reverse

from web.models import Tree


class Vendor(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    account_number = models.CharField('our account number', max_length=100, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('inventory:vendor', args=[self.pk])


class Category(Tree):
    """A kind of part. Its attributes, and those of the categories above it, are what its parts fill in."""
    class Meta(Tree.Meta):
        verbose_name_plural = 'categories'
        constraints = [models.UniqueConstraint(fields=['parent', 'name'], name='unique_category_name')]

    def get_absolute_url(self):
        return reverse('inventory:category', args=[self.pk])

    def all_attributes(self):
        """Its attributes and those it gets from above: the top category's first."""
        chain = self.chain()
        depth = {c.pk: i for i, c in enumerate(chain)}
        return sorted(Attribute.objects.filter(category__in=chain).select_related('category'),
                      key=lambda a: (depth[a.category_id], a.position, a.pk))


class Attribute(models.Model):
    """Something the parts and assets of a category, and those of every category under it, fill in, e.g. Resistance in Ω."""
    class Kind(models.TextChoices):
        TEXT = 'text', 'Text'
        INTEGER = 'integer', 'Whole number'
        DECIMAL = 'decimal', 'Number (with decimals)'
        CHOICE = 'choice', 'Choice from a list'
        YESNO = 'yesno', 'Yes / no'
        AUTO = 'auto', 'Auto number (an ID)'
        INTERACTS = 'interacts', 'Interacts with parts of a category'
        LINK = 'link', 'Link to a part or an asset'

    class LinksTo(models.TextChoices):
        PART = 'part', 'A part (of any category)'
        ASSET = 'asset', 'An asset (a tool, lab equipment…)'

    NUMERIC = (Kind.INTEGER, Kind.DECIMAL)
    LINKS = (Kind.INTERACTS, Kind.LINK)   # what parts fill in are other parts (or assets), not a value

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=100)
    kind = models.CharField('type', max_length=10, choices=Kind, default=Kind.TEXT)
    unit = models.CharField(max_length=20, blank=True)
    choices = models.TextField(blank=True)
    prefix = models.CharField(max_length=20, blank=True)
    digits = models.PositiveSmallIntegerField(default=5)
    required = models.BooleanField(default=False)
    help = models.CharField(max_length=200, blank=True)
    target = models.ForeignKey(Category, null=True, blank=True, on_delete=models.CASCADE, related_name='interactions',
                               verbose_name='interacts with')
    links_to = models.CharField(max_length=10, choices=LinksTo, blank=True)
    reverse_name = models.CharField('name on the other side', max_length=100, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'pk']

    def __str__(self):
        return self.name

    @property
    def is_link(self):
        return self.kind in self.LINKS

    @property
    def to_assets(self):
        return self.kind == self.Kind.LINK and self.links_to == self.LinksTo.ASSET

    def other_side(self):
        """What the parts or assets linked to call this attribute."""
        return self.reverse_name or f'{self.name} (of {self.category.name})'

    def candidates(self):
        """What may be linked to with this attribute: the target category's parts (and below), every part, or assets."""
        if self.kind == self.Kind.INTERACTS:
            return Part.objects.filter(category_id__in=self.target.below(), active=True) if self.target else Part.objects.none()
        if self.to_assets:
            from assets.models import Asset
            return Asset.objects.exclude(status='retired')
        return Part.objects.filter(active=True)

    def choice_list(self):
        return [line.strip() for line in self.choices.splitlines() if line.strip()]

    def clean_value(self, raw):
        """(text, number) to keep for ``raw``, ('', None) when empty; refused when it doesn't fit."""
        from decimal import Decimal, InvalidOperation

        from django.core.exceptions import ValidationError
        text = str(raw if raw is not None else '').strip()
        if not text:
            return '', None
        if self.kind in self.NUMERIC:
            try:
                number = Decimal(text.replace(',', '.'))
            except InvalidOperation:
                raise ValidationError(f'{self.name}: "{text}" is not a number.')
            if not number.is_finite():
                raise ValidationError(f'{self.name}: "{text}" is not a number.')
            if self.kind == self.Kind.INTEGER and number != number.to_integral_value():
                raise ValidationError(f'{self.name}: "{text}" is not a whole number.')
            number = number.to_integral_value() if self.kind == self.Kind.INTEGER else number.normalize()
            return f'{number:f}', number
        if self.kind == self.Kind.CHOICE:
            match = next((c for c in self.choice_list() if c.lower() == text.lower()), None)
            if match is None:
                raise ValidationError(f'{self.name}: "{text}" is not one of its choices.')
            return match, None
        if self.kind == self.Kind.YESNO:
            if text.lower() not in ('yes', 'no'):
                raise ValidationError(f'{self.name}: yes or no.')
            return text.capitalize(), None
        return text[:200], None

    def auto_value(self, number):
        """An auto number as shown and kept: ID-00042."""
        return f'{self.prefix}{number:0{self.digits}d}'

    def next_number(self):
        """The next auto number of this attribute: one more than the highest given to a part or an asset."""
        from django.db.models import Max
        from assets.models import AssetValue
        highest = max(self.values.aggregate(n=Max('number'))['n'] or 0, AssetValue.objects.filter(attribute=self).aggregate(n=Max('number'))['n'] or 0)
        return int(highest) + 1

    def show(self, value):
        """A value as shown: with its unit."""
        return f'{value} {self.unit}' if value and self.unit and self.kind in self.NUMERIC else value


class Location(Tree):
    description = models.CharField(max_length=200, blank=True)

    class Meta(Tree.Meta):
        constraints = [models.UniqueConstraint(fields=['parent', 'name'], name='unique_location_name')]

    def get_absolute_url(self):
        return reverse('inventory:location', args=[self.pk])


class Part(models.Model):
    class Unit(models.TextChoices):
        PCS = 'pcs', 'pieces'
        M = 'm', 'metres'
        KG = 'kg', 'kilograms'
        L = 'l', 'litres'
        SET = 'set', 'sets'
        ROLL = 'roll', 'rolls'

    number = models.CharField('part number', max_length=100)
    description = models.CharField(max_length=300, blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name='parts')
    manufacturer = models.CharField(max_length=200, blank=True)
    mpn = models.CharField('manufacturer part number', max_length=200, blank=True)
    unit = models.CharField(max_length=10, choices=Unit, default=Unit.PCS)
    datasheet = models.URLField(blank=True)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name='parts')
    vendor_number = models.CharField("vendor's part number", max_length=200, blank=True)
    price = models.DecimalField('last price', max_digits=12, decimal_places=4, null=True, blank=True)
    minimum = models.DecimalField('minimum stock', max_digits=12, decimal_places=3, default=0)
    reorder_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']
        constraints = [models.UniqueConstraint(Lower('number'), name='unique_part_number',
                                               violation_error_message='There is already a part with this number.')]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse('inventory:part', args=[self.pk])

    @property
    def on_hand(self):
        return self.stock.aggregate(n=Sum('quantity'))['n'] or Decimal(0)


class PartValue(models.Model):
    """What a part fills in for an attribute of its category (``number`` too, for numbers: to sort and filter by)."""
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='values')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=200)
    number = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['part', 'attribute'], name='unique_part_value')]

    def __str__(self):
        return f'{self.attribute}: {self.value}'


class PartLink(models.Model):
    """A part naming another part with an "interacts with" attribute or a link (a pin that mates with a socket)."""
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='links')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='links')
    target = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='linked_from')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['part', 'attribute', 'target'], name='unique_part_link')]

    def __str__(self):
        return f'{self.part} {self.attribute} {self.target}'


class Stock(models.Model):
    """How many of a part are in a location now."""
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='stock')
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='stock')
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    class Meta:
        ordering = ['part__number', 'location__name']
        constraints = [models.UniqueConstraint(fields=['part', 'location'], name='unique_stock')]

    def __str__(self):
        return f'{self.part} × {self.quantity} in {self.location}'


class Movement(models.Model):
    """One change of stock: into a location, out of one, or from one to another."""
    class Kind(models.TextChoices):
        RECEIVED = 'received', 'Received'
        ADDED = 'added', 'Added'
        MOVED = 'moved', 'Moved'
        USED = 'used', 'Used'
        COUNTED = 'counted', 'Counted'

    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='movements')
    kind = models.CharField(max_length=10, choices=Kind)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)   # signed for a count: the difference it made
    source = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    target = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    note = models.CharField(max_length=300, blank=True)
    reference = models.CharField(max_length=100, blank=True)   # e.g. the order it was received for
    url = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at', '-pk']

    def __str__(self):
        return f'{self.get_kind_display()} {self.quantity} {self.part}'
