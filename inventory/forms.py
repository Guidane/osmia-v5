from django import forms
from django.utils.html import format_html, format_html_join

from web.forms import TreeForm, tree_choices

from .models import Attribute, Branch, Category, Family, Location, Part, Vendor, choices_of_parts, part_or_family


class PartOrFamilyInput(forms.TextInput):
    """A box for a part number or a family name, suggesting both."""
    def render(self, name, value, attrs=None, renderer=None):
        listed = f'{(attrs or {}).get("id") or name}-list'
        box = super().render(name, value, {**(attrs or {}), 'list': listed, 'autocomplete': 'off'}, renderer)
        return box + format_html('<datalist id="{}">{}</datalist>', listed,
                                 format_html_join('', '<option value="{}">{}</option>', choices_of_parts()))


class PartOrFamilyField(forms.CharField):
    """A part, or a family of them, by its number or name."""
    widget = PartOrFamilyInput

    def prepare_value(self, value):
        return getattr(value, 'number', value)

    def to_python(self, value):
        text = super().to_python(value)
        found = part_or_family(text)
        if text and found is None:
            raise forms.ValidationError(f'There is no part or family "{text}".')
        return found


class PartOrFamilyForm(forms.ModelForm):
    """A form of something that names a part or a family (``used``)."""
    used = PartOrFamilyField(required=False, label='Part or family')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault('used', self.instance.used)

    def save(self, commit=True):
        self.instance.used = self.cleaned_data.get('used')
        return super().save(commit)


def attribute_field(attribute, required, initial):
    """The input for an attribute: its kind's, labelled with its unit."""
    label = f'{attribute.name} ({attribute.unit})' if attribute.unit and attribute.kind in Attribute.NUMERIC else attribute.name
    common = {'label': label, 'required': required, 'initial': initial, 'help_text': attribute.help}
    if attribute.kind == Attribute.Kind.AUTO:   # given, not filled in
        common['required'] = False
        return forms.CharField(disabled=True, **common)
    if attribute.kind == Attribute.Kind.LINK and not attribute.to_assets:   # any part: by part number
        return forms.CharField(widget=forms.TextInput(attrs={'list': 'part-numbers', 'autocomplete': 'off',
                                                             'placeholder': 'Part numbers, separated by commas'}), **common)
    if attribute.is_link:   # a category's parts, or assets: picked from a list
        choices = [(c.pk, str(c) if attribute.to_assets else f'{c.number} {c.description}'.strip()) for c in attribute.candidates()]
        return forms.MultipleChoiceField(choices=choices, widget=forms.SelectMultiple(attrs={'size': min(max(len(choices), 2), 6)}), **common)
    if attribute.kind == Attribute.Kind.CHOICE:
        return forms.ChoiceField(choices=[('', '—')] + [(c, c) for c in attribute.choice_list()], **common)
    if attribute.kind == Attribute.Kind.YESNO:
        return forms.ChoiceField(choices=[('', '—'), ('Yes', 'Yes'), ('No', 'No')], **common)
    if attribute.kind == Attribute.Kind.INTEGER:
        return forms.CharField(widget=forms.TextInput(attrs={'inputmode': 'numeric'}), **common)
    if attribute.kind == Attribute.Kind.DECIMAL:
        return forms.CharField(widget=forms.TextInput(attrs={'inputmode': 'decimal'}), **common)
    return forms.CharField(max_length=200, **common)


class AttributesForm(TreeForm):
    """A form for a part or an asset: the attributes of its category, and of those above it, are filled in on it too."""

    def __init__(self, *args, **kwargs):
        from .attributes import store_for
        super().__init__(*args, **kwargs)
        node = self.instance.category
        if self.is_bound:
            picked = str(self.data.get('category') or '')
            node = Category.objects.filter(pk=picked).first() if picked.isdigit() else None
        # The attributes shown were those of ``attributes_of``: a category picked since has its own still to fill in.
        self.shown_category = node.pk if node else ''
        moved = self.is_bound and str(self.data.get('attributes_of', '')) != str(self.shown_category)
        self.attributes = node.all_attributes() if node else []
        self.store = store_for(self.instance)
        have = self.store.values(self.instance) if self.instance.pk else {}
        for a in self.attributes:
            if a.is_link and self.instance.pk:
                linked = self.store.linked(a, self.instance)
                have[a.pk] = [x.pk for x in linked] if a.kind == Attribute.Kind.INTERACTS or a.to_assets else ', '.join(x.number for x in linked)
            self.fields[f'attr_{a.pk}'] = attribute_field(a, a.required and not moved, have.get(a.pk))

    def attribute_fields(self):
        return [self[f'attr_{a.pk}'] for a in self.attributes]

    def clean(self):
        data = super().clean()
        self.attribute_values, self.attribute_links = {}, {}
        for a in self.attributes:
            raw = data.get(f'attr_{a.pk}')
            if a.kind == Attribute.Kind.AUTO:
                continue
            try:
                if a.is_link:
                    self.attribute_links[a.pk] = self._linked(a, raw)
                else:
                    self.attribute_values[a.pk] = a.clean_value(raw)
            except forms.ValidationError as exc:
                self.add_error(f'attr_{a.pk}', exc)
        return data

    def _linked(self, attribute, raw):
        """The parts or assets a link attribute names: picked from its list, or part numbers separated by commas."""
        if attribute.kind == Attribute.Kind.LINK and not attribute.to_assets:
            numbers = [n.strip() for n in str(raw or '').split(',') if n.strip()]
            found = {n: Part.objects.filter(number__iexact=n).first() for n in numbers}
            missing = [n for n, part in found.items() if part is None]
            if missing:
                raise forms.ValidationError(f'There is no part {", ".join(missing)}.')
            return list(found.values())
        return list(attribute.candidates().filter(pk__in=raw or []))

    def save(self, commit=True):
        obj = super().save()
        self.store.save(obj, self.attributes, self.attribute_values, self.attribute_links)
        return obj


class PartForm(AttributesForm):
    """A part, and the attributes of its category (and of those above it)."""
    tree_fields = {'category': (Category, {'kind': Category.Kind.PARTS})}

    class Meta:
        model = Part
        fields = ['number', 'description', 'category', 'kin', 'manufacturer', 'mpn', 'unit', 'datasheet', 'vendor', 'vendor_number',
                  'price', 'minimum', 'reorder_quantity', 'notes', 'active']
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}

    kin = forms.ChoiceField(label='Family', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vendor'].queryset = Vendor.objects.filter(active=True) | Vendor.objects.filter(pk=self.instance.vendor_id)
        branches = {}
        for b in Branch.objects.select_related('family'):
            branches.setdefault(b.family_id, []).append((f'b{b.pk}', b.number))
        self.fields['kin'].choices = [('', '—')] + [(f.name, [(f'f{f.pk}', f'{f.name} (any)')] + branches.get(f.pk, []))
                                                    for f in Family.objects.all()]
        part = self.instance
        self.initial['kin'] = f'b{part.branch_id}' if part.branch_id else f'f{part.family_id}' if part.family_id else ''

    def clean_kin(self):
        """The family, and the branch of it when one is picked."""
        picked = self.cleaned_data['kin']
        branch = Branch.objects.filter(pk=picked[1:]).first() if picked.startswith('b') else None
        self.instance.branch = branch
        self.instance.family = branch.family if branch else Family.objects.filter(pk=picked[1:] if picked.startswith('f') else 0).first()
        return picked


class AttributeForm(forms.ModelForm):
    """An attribute of a category. Its name can't be one the categories above or under it use; changing its type or
    choices is refused while what parts and assets filled in wouldn't fit."""
    class Meta:
        model = Attribute
        fields = ['name', 'kind', 'unit', 'choices', 'prefix', 'digits', 'target', 'links_to', 'reverse_name', 'required', 'help']
        widgets = {'choices': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, category, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = category
        self.fields['target'].choices = tree_choices(Category, kind=Category.Kind.PARTS)
        self.fields['digits'].required = False

    def _values(self):
        """What parts and assets filled in for it."""
        return list(self.instance.values.select_related('part')) + list(self.instance.asset_values.select_related('asset'))

    def clean_digits(self):
        return self.cleaned_data.get('digits') or 5

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        related = [c.pk for c in self.category.chain()] + list(self.category.below())
        clash = Attribute.objects.filter(category__in=related, name__iexact=name).exclude(pk=self.instance.pk).select_related('category').first()
        if clash:
            raise forms.ValidationError(f'{clash.category.name} already has an attribute "{clash.name}".')
        return name

    def clean(self):
        data = super().clean()
        trial = Attribute(name=data.get('name') or self.instance.name, kind=data.get('kind'), choices=data.get('choices', ''),
                          links_to=data.get('links_to', ''))
        was_link = self.instance.pk and self.instance.is_link
        if trial.kind == Attribute.Kind.CHOICE and not trial.choice_list():
            self.add_error('choices', 'List the choices, one per line.')
        elif trial.kind == Attribute.Kind.INTERACTS and not data.get('target'):
            self.add_error('target', 'Pick the category whose parts it interacts with.')
        elif trial.kind == Attribute.Kind.LINK and not data.get('links_to'):
            self.add_error('links_to', 'Say what it links to.')
        elif was_link and (trial.kind != self.instance.kind or trial.links_to != self.instance.links_to
                           or (trial.kind == Attribute.Kind.INTERACTS and data.get('target') != self.instance.target)):
            if self.instance.links.exists() or self.instance.asset_links.exists() or self.instance.asset_targets.exists():
                raise forms.ValidationError('Things link with it already: take those links away first.')
        elif self.instance.pk and (trial.is_link or (trial.kind == Attribute.Kind.AUTO and self.instance.kind != Attribute.Kind.AUTO)):
            if self._values():
                raise forms.ValidationError('It is filled in already: empty those first.')
        elif self.instance.pk and trial.kind != Attribute.Kind.AUTO:
            misfits = []
            for v in self._values():
                try:
                    trial.clean_value(v.value)
                except forms.ValidationError:
                    misfits.append(f'{getattr(v, "part", None) or v.asset}: "{v.value}"')
            if misfits:
                raise forms.ValidationError(f'{len(misfits)} would not fit any more: '
                                            + ', '.join(misfits[:3]) + (', …' if len(misfits) > 3 else '') + '. Change those first.')
        return data

    def save(self, commit=True):
        attribute = super().save(commit=False)
        attribute.category = self.category
        if not attribute.pk:
            attribute.position = self.category.attributes.count()
        if not attribute.is_link:
            attribute.target, attribute.links_to, attribute.reverse_name = None, '', ''
        elif attribute.kind == Attribute.Kind.LINK:
            attribute.target = None
        attribute.save()
        if attribute.kind == Attribute.Kind.AUTO:   # those in the category get their number now, oldest first
            from assets.models import Asset

            from .attributes import number_up
            below = self.category.below()
            for v in self._values():
                v.value = attribute.auto_value(int(v.number))
                v.save(update_fields=['value'])
            number_up(attribute, list(Part.objects.filter(category_id__in=below).order_by('pk'))
                      + list(Asset.objects.filter(category_id__in=below).order_by('pk')))
            return attribute
        for v in self._values():   # kept as the (new) type keeps them, e.g. "10.0" → "10"
            v.value, v.number = attribute.clean_value(v.value)
            v.save(update_fields=['value', 'number'])
        return attribute


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ['name', 'code', 'website', 'email', 'phone', 'address', 'account_number', 'notes', 'active']
        widgets = {'address': forms.Textarea(attrs={'rows': 3}), 'notes': forms.Textarea(attrs={'rows': 3})}


class LocationForm(TreeForm):
    tree_fields = {'parent': Location}

    class Meta:
        model = Location
        fields = ['name', 'parent', 'description']
        labels = {'parent': 'Inside'}

    def clean_parent(self):
        return self._not_inside_itself('parent', "A location can't be inside itself.")


class FamilyForm(forms.ModelForm):
    """A family of parts: its name."""
    class Meta:
        model = Family
        fields = ['name']

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if Part.objects.filter(number__iexact=name).exists():
            raise forms.ValidationError('That is a part number: give the family a name of its own.')
        return name


class BranchForm(forms.ModelForm):
    """A branch of a family: its name."""
    class Meta:
        model = Branch
        fields = ['name']

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.family = family

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if Branch.objects.filter(family=self.instance.family, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(f'{self.instance.family} has a branch {name} already.')
        return name


class CategoryForm(TreeForm):
    """A category of parts or of assets (``kind``), under one of the same kind."""
    class Meta:
        model = Category
        fields = ['name', 'parent']
        labels = {'parent': 'Part of'}

    def __init__(self, *args, kind, **kwargs):
        self.tree_fields = {'parent': (Category, {'kind': kind})}
        super().__init__(*args, **kwargs)
        self.instance.kind = kind

    def clean_parent(self):
        return self._not_inside_itself('parent', "A category can't be part of itself.")
