from django import forms

from inventory.forms import PartOrFamilyField, PartOrFamilyForm, PartOrFamilyInput

from .models import Connector, Device


class DeviceForm(PartOrFamilyForm):
    """A device, and (ticked) a unit of it made as an asset, with the next free asset tag."""
    make_asset = forms.BooleanField(required=False, label='Make an asset')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['used'].label = 'As a part'
        if self.instance.pk:
            self.fields['make_asset'].label = 'Make another asset'

    def add_unit(self, device):
        """The unit asked for, as an asset of the device: <number>-001, -002, …"""
        from assets.models import Asset
        from assets.service import next_tag
        if self.cleaned_data.get('make_asset'):
            return Asset.objects.create(number=next_tag(device.number), name=device.name, device=device,
                                        version=device.version or None, manufacturer=device.manufacturer, model=device.model,
                                        kind=Asset.Kind.LAB if device.origin == 'external' else Asset.Kind.DEVICE)

    class Meta:
        model = Device
        fields = ['number', 'name', 'origin', 'description', 'manufacturer', 'model', 'used', 'colour', 'notes']
        widgets = {'description': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 3}),
                   'colour': forms.TextInput(attrs={'type': 'color'})}


class GenderField(PartOrFamilyField):
    """A part, a family or one of its genders; "<family> / pin" or "/ socket" makes that gender when it hasn't one."""
    def to_python(self, value):
        from inventory.picker import with_gender
        return super().to_python(with_gender(value))


class FamilyPicker(PartOrFamilyInput):
    """The family (or one of its genders) a connector is, picked in the family popup (``inventory.picker``); what it is
    now on a button that opens it."""
    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import format_html

        from inventory import picker
        from inventory.models import Part, part_or_family
        attrs = attrs or {}
        found = part_or_family(value) if value else None   # a part: shown as its gender (else family) in the popup
        current = (found.branch or found.family or found).number if isinstance(found, Part) else value or ''
        box = forms.HiddenInput().render(name, value, {**attrs, 'data-family-value': '', 'data-current': current}, renderer)
        return format_html(
            '{}<span class="family-pick"><button type="button" class="btn" data-family-open>{}</button>'
            '<button type="button" class="btn ghost" data-family-clear title="None"{}>✕</button></span>{}',
            box, value or 'Choose…', '' if value else ' hidden', picker.dialog())


class ConnectorForm(PartOrFamilyForm):
    used = GenderField(required=False, label='Family', widget=FamilyPicker)

    pins = forms.CharField(required=False, label='Pins',
                           widget=forms.TextInput(attrs={'placeholder': 'How many (e.g. 9), or their numbers: A1, A2, B1'}))

    class Meta:
        model = Connector
        fields = ['designator', 'name', 'used']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields['pins']

    def clean_designator(self):
        designator = self.cleaned_data['designator'].strip()
        others = Connector.objects.filter(device_id=self.instance.device_id, designator__iexact=designator).exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError(f'This device already has a {designator}.')
        return designator

    def clean_pins(self):
        text = self.cleaned_data.get('pins', '').strip()
        if not text:
            return []
        if text.isdigit():
            if not 0 < int(text) <= 500:
                raise forms.ValidationError('Between 1 and 500 pins.')
            return [str(n) for n in range(1, int(text) + 1)]
        numbers = [n.strip() for n in text.replace(';', ',').split(',') if n.strip()]
        if len(set(n.lower() for n in numbers)) != len(numbers):
            raise forms.ValidationError('A pin number is there twice.')
        return numbers
