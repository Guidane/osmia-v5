"""Assets: the list (by kind, category and status, those due for calibration), an asset's page (checking it out and
back, calibration, sending it away, putting it on an order, a harness's checklist, its history and what links to it)."""
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inventory import attributes as kept
from inventory.attributes import AssetStore
from inventory.forms import AttributesForm
from inventory.models import Attribute, Category, Location, Part
from web import excel
from web.shortcuts import errors
from web.forms import initial_for

from . import service
from .models import Asset


class AssetForm(AttributesForm):
    """An asset, and the attributes of its category (and of those above it)."""
    tree_fields = {'category': Category, 'location': Location}

    class Meta:
        model = Asset
        fields = ['number', 'name', 'kind', 'category', 'manufacturer', 'model', 'serial', 'device', 'harness', 'version', 'location', 'keeper',
                  'vendor', 'vendor_number', 'price', 'calibrated_on', 'calibration_months', 'built_on', 'notes']
        widgets = {'calibrated_on': forms.DateInput(attrs={'type': 'date'}), 'built_on': forms.DateInput(attrs={'type': 'date'}),
                   'notes': forms.Textarea(attrs={'rows': 3})}

    on_order = forms.BooleanField(required=False, label='Still to be bought', help_text='It is "On order" until an order brings it.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields['on_order']

    def save(self, commit=True):
        if self.cleaned_data.get('on_order'):
            self.instance.status = Asset.Status.ORDERED
        return super().save(commit)



@login_required
def asset_list(request):
    q = request.GET.get('q', '').strip()
    found = Asset.objects.select_related('category', 'location', 'keeper', 'holder')
    if q:
        found = found.filter(Q(number__icontains=q) | Q(name__icontains=q) | Q(manufacturer__icontains=q) | Q(model__icontains=q)
                             | Q(serial__icontains=q))
    kind = request.GET.get('kind', '')
    if kind in Asset.Kind.values:
        found = found.filter(kind=kind)
    category = Category.objects.filter(pk=request.GET.get('category') or 0).first()
    if category is not None:
        found = found.filter(category_id__in=category.below())
    status = request.GET.get('status', '')
    if status in Asset.Status.values:
        found = found.filter(status=status)
    elif not request.GET.get('all'):
        found = found.exclude(status=Asset.Status.RETIRED)
    attributes = category.all_attributes() if category else []
    if category is not None:
        found = kept.filtered(found, attributes, request.GET, AssetStore())
    assets = list(found)
    if request.GET.get('due'):
        due = {a.pk for a in service.due()}
        assets = [a for a in assets if a.pk in due]
    if request.GET.get('export'):
        return excel.download('assets', [('Assets', ['Asset tag', 'Name', 'Kind', 'Category', 'Manufacturer', 'Model', 'Serial number',
                                                     'Kept at', 'Keeper', 'Status', 'Out with', 'Calibrated', 'Due'],
                                          [(a.number, a.name, a.get_kind_display(), a.category.path if a.category else '', a.manufacturer, a.model,
                                            a.serial, a.location.path if a.location else '', str(a.keeper or ''), a.get_status_display(),
                                            str(a.holder or ''), a.calibrated_on, a.calibration_due) for a in assets])])
    return render(request, 'assets/list.html', {
        'rows': kept.columns(assets, attributes, AssetStore()), 'attributes': attributes, 'filters': kept.filters(attributes, request.GET),
        'q': q, 'kind': kind, 'kinds': Asset.Kind.choices, 'category': category, 'status': status, 'categories': Category.ordered(),
        'statuses': Asset.Status.choices})


@login_required
def asset_form(request, pk=None):
    item = get_object_or_404(Asset, pk=pk) if pk else None
    form = AssetForm(request.POST or None, instance=item,
                     initial=initial_for(item, **{k: request.GET.get(k) for k in ('category', 'kind', 'device', 'number', 'name', 'version')}))
    if request.method == 'POST' and not request.POST.get('refresh') and form.is_valid():   # refresh: its type changed
        item = form.save()
        messages.success(request, f'{item} is saved.')
        return redirect(item)
    numbers = Part.objects.filter(active=True).values_list('number', 'description')[:5000] \
        if any(a.kind == Attribute.Kind.LINK and not a.to_assets for a in form.attributes) else []
    return render(request, 'inventory/attributes_form.html', {'form': form, 'title': f'Change {item}' if item else 'New asset',
                                                              'back': item.get_absolute_url() if item else None, 'part_numbers': numbers})


@login_required
def asset(request, pk):
    item = get_object_or_404(Asset.objects.select_related('category', 'location', 'keeper', 'holder', 'device', 'harness'), pk=pk)
    checks = list(item.checks.all())
    return render(request, 'assets/asset.html', {
        'asset': item, 'events': item.events.select_related('user')[:100], 'linked_here': kept.linked_here(item),
        'attributes': kept.shown(item, item.category), 'order_lines': item.order_lines.select_related('order__vendor'),
        'checks': checks, 'placed': sum(c.placed for c in checks), 'verified': sum(c.verified for c in checks),
        'people': get_user_model().objects.filter(is_active=True), 'today': date.today()})


@login_required
@require_POST
def act(request, pk):
    """Check it out or back, record a calibration, send it away, put it on an order."""
    item = get_object_or_404(Asset, pk=pk)
    post, action, note = request.POST, request.POST.get('action'), request.POST.get('note', '')
    try:
        if action == 'order':
            from orders.service import order_asset
            line = order_asset(item, request.user)
            messages.success(request, f'{item} is on {line.order} ({line.order.vendor}).')
            return redirect(line.order)
        if action == 'out':
            to = get_user_model().objects.filter(pk=post.get('to') or 0, is_active=True).first()
            service.check_out(item, request.user, to, note)
        elif action == 'back':
            service.bring_back(item, request.user, note)
        elif action == 'calibrated':
            on = post.get('on')
            service.calibrated(item, request.user, date.fromisoformat(on) if on else None, note)
        elif action in service.AWAY:
            service.send_away(item, request.user, action, note)
        else:
            raise ValidationError('What happened to it?')
    except ValueError:
        messages.error(request, 'That is not a date.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)


@login_required
@require_POST
def checklist(request, pk):
    """A harness built: its wires ticked as placed, then verified; when every one is, it is available."""
    item = get_object_or_404(Asset, pk=pk)
    checks = list(item.checks.all())
    try:
        with transaction.atomic():
            for check in checks:
                check.placed = f'placed_{check.pk}' in request.POST
                check.verified = f'verified_{check.pk}' in request.POST
                if check.verified and not check.placed:
                    raise ValidationError(f'{check.wire}: place it before verifying it.')
                check.save(update_fields=['placed', 'verified'])
            if checks and all(c.verified for c in checks) and item.status == Asset.Status.BUILDING:
                item.status = Asset.Status.AVAILABLE
                item.save(update_fields=['status'])
                service.event(item, 'built', request.user, 'every wire verified')
                messages.success(request, f'{item.number}: every wire is verified.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)
