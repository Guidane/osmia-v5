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


def _genders(family):
    """A family's genders to pick from: its own, and pin and socket when it has none of that side yet (made when
    picked: see ``GenderField``)."""
    out = [{'name': b.name, 'value': b.number, 'socket': b.contacts == 'socket'} for b in family.branches.all()]
    sides = {b.contacts for b in family.branches.all()} | {b.name.lower() for b in family.branches.all()}
    for side in ('pin', 'socket'):
        if side not in sides:
            out.append({'name': side, 'value': f'{family.name} / {side}', 'socket': side == 'socket'})
    return out


class GenderField(PartOrFamilyField):
    """A part, a family or one of its genders; "<family> / pin" or "/ socket" makes that gender when it hasn't one."""
    def to_python(self, value):
        from inventory.models import Branch, Family
        text = (value or '').strip()
        family, _, side = text.rpartition(' / ')
        if family and side.lower() in ('pin', 'socket'):
            found = Family.objects.filter(name__iexact=family.strip()).first()
            if found and not found.branches.filter(name__iexact=side).exists():
                Branch.objects.create(family=found, name=side.lower(), contacts=side.lower())
        return super().to_python(value)


class FamilyPicker(PartOrFamilyInput):
    """The family (or one of its genders) a connector is, picked in a popup that shows each family's face; what it is
    now on a button that opens it."""
    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import format_html, json_script

        from inventory.faces import face_of, natural
        from inventory.models import Family, FamilyBranch, Part, part_or_family
        from web.templatetags.osmia import fresh
        attrs = attrs or {}
        found = part_or_family(value) if value else None   # a part: shown as its gender (else family) in the popup
        current = (found.branch or found.family or found).number if isinstance(found, Part) else value or ''
        box = forms.HiddenInput().render(name, value, {**attrs, 'data-family-value': '', 'data-current': current}, renderer)
        families = [{'name': f.name, 'face': face_of(f), 'branch': f.group_id, 'genders': _genders(f)}
                    for f in sorted(Family.objects.prefetch_related('branches'), key=lambda f: natural(f.name))]
        tree = [{'id': b.pk, 'name': b.name, 'depth': depth, 'below': sorted(b.below())} for b, depth in FamilyBranch.ordered()]
        return format_html(
            '{}<span class="family-pick"><button type="button" class="btn" data-family-open>{}</button>'
            '<button type="button" class="btn ghost" data-family-clear title="None"{}>✕</button></span>'
            '<dialog class="finder family-finder" aria-label="Family"><div class="finder-head"><h3>Family</h3>'
            '<input type="search" data-family-q placeholder="Search" aria-label="Search" autocomplete="off">'
            '<span class="spacer"></span><button type="button" class="btn small ghost" data-family-close title="Close">✕</button></div>'
            '<div class="finder-body"><nav class="finder-tree" data-family-tree aria-label="Branches"></nav>'
            '<div class="family-cards" data-family-cards></div></div></dialog>'
            '{}'
            '<script src="{}"></script><script src="{}"></script>',
            box, value or 'Choose…', '' if value else ' hidden', json_script({'families': families, 'tree': tree}, 'family-data'), fresh('harnesses/pinout.js'),
            fresh('devices/family_picker.js'))


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
