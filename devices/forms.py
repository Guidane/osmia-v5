from django import forms

from .models import Connector, Device


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = ['number', 'name', 'origin', 'description', 'manufacturer', 'model', 'part', 'colour', 'notes']
        widgets = {'description': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 3}),
                   'colour': forms.TextInput(attrs={'type': 'color'})}


class ConnectorForm(forms.ModelForm):
    pins = forms.CharField(required=False, label='Pins',
                           widget=forms.TextInput(attrs={'placeholder': 'How many (e.g. 9), or their numbers: A1, A2, B1'}))

    class Meta:
        model = Connector
        fields = ['designator', 'name', 'part']

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
