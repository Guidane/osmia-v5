from django import forms
from django.contrib.auth import password_validation

from web.forms import TreeForm, tree_choices

from .models import Department, User


class ProfileForm(forms.ModelForm):
    """What people can change about themselves."""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'job_title', 'phone']


class UserForm(forms.ModelForm):
    """An administrator making or changing someone: their department, whether they are an administrator, whether they
    can log in, a password (needed for someone new; empty keeps theirs)."""
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(render_value=False), required=False, strip=False)
    password2 = forms.CharField(label='Password again', widget=forms.PasswordInput(render_value=False), required=False, strip=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'job_title', 'phone', 'department', 'is_superuser', 'is_active']
        labels = {'is_superuser': 'Administrator', 'is_active': 'Can log in'}

    def __init__(self, *args, by=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.by = by
        self.fields['department'].choices = tree_choices(Department)
        if self.instance.pk:
            self.fields['password1'].widget.attrs['placeholder'] = 'Empty: it stays as it is'

    def clean(self):
        data = super().clean()
        p1, p2 = data.get('password1'), data.get('password2')
        if not self.instance.pk and not p1:
            self.add_error('password1', 'Give them a password to log in with.')
        if p1 or p2:
            if p1 != p2:
                self.add_error('password2', 'The two passwords are not the same.')
            else:
                try:
                    password_validation.validate_password(p1, self.instance)
                except forms.ValidationError as exc:
                    self.add_error('password1', exc)
        if self.by is not None and self.instance.pk == self.by.pk and (not data.get('is_superuser') or not data.get('is_active')):
            raise forms.ValidationError("You can't take away your own administrator rights or log-in: ask another administrator.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = user.is_superuser   # administrators can use /admin/
        if self.cleaned_data.get('password1'):
            user.set_password(self.cleaned_data['password1'])
        user.save()
        return user


class DepartmentForm(TreeForm):
    tree_fields = {'parent': Department}

    class Meta:
        model = Department
        fields = ['name', 'parent', 'manager', 'description']
        labels = {'parent': 'Part of'}
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['manager'].queryset = User.objects.filter(is_active=True)

    def clean_parent(self):
        return self._not_inside_itself('parent', "A department can't be part of itself.")
