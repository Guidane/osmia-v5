"""Forms shared by the parts of Osmia: dropdowns of a tree."""
from django import forms


def tree_choices(model):
    """A tree's nodes for a dropdown, indented under their parents."""
    return [('', '—')] + [(node.pk, '   ' * depth + node.name) for node, depth in model.ordered()]


class TreeForm(forms.ModelForm):
    """A form whose ``tree_fields`` ({field name: model}) are dropdowns of a tree."""
    tree_fields = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, model in self.tree_fields.items():
            self.fields[name].choices = tree_choices(model)

    def _not_inside_itself(self, name, message):
        node = self.cleaned_data[name]
        if node is not None and self.instance.pk and node.pk in self.instance.below():
            raise forms.ValidationError(message)
        return node


def initial_for(instance, **values):
    """What a form starts with for something new (e.g. the parent from ?parent=): nothing for something that is
    there already, whose own values are shown."""
    if instance is not None:
        return {}
    return {k: v for k, v in values.items() if v not in (None, '')}
