"""Orders: the list (what is still to come, what is late, requests to order), an order's page (its details, then its
lines while it is a draft; placing, receiving, cancelling) and making one: an order of one's own, or a request asking
someone else to order what is described."""
from datetime import date
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from assets.models import Asset
from budgets.models import Budget
from inventory import stock
from inventory.models import Category, Location, Part, Vendor
from web import excel
from web.forms import initial_for
from web.templatetags.osmia import qty
from web.shortcuts import errors

from . import service
from .models import Order, OrderLine

REQUESTS = Q(kind=Order.Kind.REQUEST, status=Order.Status.DRAFT)
SHOWN = {'open': ('Still to come', Q(status__in=Order.OPEN)), 'requests': ('Requests', REQUESTS),
         'draft': ('Drafts', Q(status=Order.Status.DRAFT, kind=Order.Kind.ORDER)),
         'received': ('Received', Q(status=Order.Status.RECEIVED)), 'all': ('All', Q())}


class OrderForm(forms.ModelForm):
    """An order's details (a request's: who should order it too, while it is a draft). What a request asked for stays as
    it was sent."""
    class Meta:
        model = Order
        fields = ['request', 'ask', 'vendor', 'budget', 'in_project', 'vendor_reference', 'expected_on', 'notes']
        widgets = {'expected_on': forms.DateInput(attrs={'type': 'date'}), 'notes': forms.Textarea(attrs={'rows': 6}),
                   'request': forms.Textarea(attrs={'rows': 4, 'placeholder': 'e.g. 20 M3x8 screws, stainless, for the rack by Friday'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vendor'].queryset = Vendor.objects.filter(active=True) | Vendor.objects.filter(pk=self.instance.vendor_id)
        self.fields['budget'].choices = [('', '—')] + [(b.pk, '   ' * depth + str(b)) for b, depth in Budget.ordered()
                                                       if b.active or b.pk == self.instance.budget_id]
        self.fields['ask'].queryset = get_user_model().objects.filter(is_active=True)
        if self.instance.kind != Order.Kind.REQUEST or self.instance.pk:
            del self.fields['request']
        if self.instance.kind != Order.Kind.REQUEST or self.instance.status != Order.Status.DRAFT:
            del self.fields['ask']
        if self.instance.pk and self.instance.status != Order.Status.DRAFT:
            self.fields['vendor'].disabled = True


class RequestForm(OrderForm):
    """Asking someone else to order: what is needed, and maybe the budget, the vendor, who should order it."""
    class Meta(OrderForm.Meta):
        fields = ['request', 'budget', 'in_project', 'vendor', 'ask']

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('instance', Order(kind=Order.Kind.REQUEST))
        super().__init__(*args, **kwargs)
        self.fields['request'].required = True


@login_required
def order_list(request):
    shown = request.GET.get('show') if request.GET.get('show') in SHOWN else 'open'
    found = Order.objects.filter(SHOWN[shown][1]).select_related('vendor').prefetch_related('lines__part', 'lines__asset')
    q = request.GET.get('q', '').strip()
    if q:
        found = found.filter(Q(number__icontains=q) | Q(vendor__name__icontains=q) | Q(vendor_reference__icontains=q) | Q(request__icontains=q)
                             | Q(lines__part__number__icontains=q) | Q(lines__asset__number__icontains=q)).distinct()
    if request.GET.get('export'):
        return excel.download('orders', [
            ('Orders', ['Order', 'Asked for', 'Vendor', 'Status', "Vendor's number", 'Ordered', 'Expected', 'Received', 'Late'],
             [(o.number, o.request, o.vendor.name if o.vendor else '', o.get_status_display(), o.vendor_reference, o.ordered_on, o.expected_on, o.received_on,
               'yes' if o.overdue else '') for o in found]),
            ('Lines', ['Order', 'Part number or asset', 'Description', 'Ordered', 'Received', 'Price each'],
             [(o.number, line.item.number, line.text, line.quantity, line.received, line.price)
              for o in found for line in o.lines.all()])])
    found = list(found[:300])
    if shown == 'open':   # late ones first, then by when they are expected
        found.sort(key=lambda o: (not o.overdue, o.expected_on or date.max, o.pk))
    from web import briefs, browse
    kept = browse.keep(request, 'q')
    nodes = [browse.node(label, f'?show={key}{kept}', Order.objects.filter(which).count(), key == shown) for key, (label, which) in SHOWN.items()]
    picked = Order.objects.filter(pk=request.GET.get('order') or 0).first()
    return render(request, 'orders/list.html', {'orders': found, 'shown': shown, 'nodes': nodes, 'q': q, 'picked': picked,
                                                'brief': briefs.of('order', picked) if picked else None,
                                                'requests': Order.objects.filter(REQUESTS).count()})


@login_required
def order_new(request):
    """Two ways: an order of one's own (its vendor, then its lines), or a request asking someone else to order."""
    start = initial_for(None, vendor=request.GET.get('vendor'), budget=request.GET.get('budget'), in_project=request.GET.get('in_project'))
    asking = request.POST.get('kind') == Order.Kind.REQUEST
    own = OrderForm(request.POST if request.method == 'POST' and not asking else None, initial=start, prefix='own')
    wish = RequestForm(request.POST if asking else None, initial=start, prefix='ask')
    del own.fields['vendor_reference'], own.fields['expected_on'], own.fields['notes']
    own.fields['vendor'].required = True
    form = wish if asking else own
    if request.method == 'POST' and form.is_valid():
        order = form.save(commit=False)
        order.created_by = request.user
        order.save()
        if asking:
            service.ask(order)
            messages.success(request, f'{order} is asked for: {order.ask or "the administrators"} will order it.')
        return redirect(order)
    return render(request, 'orders/new.html', {'own': own, 'wish': wish, 'asking': asking})


def _where(line):
    """Where a received part most likely goes: the location that holds most of it."""
    if line.asset_id:
        return line.asset.location_id
    row = line.part.stock.filter(quantity__gt=0).order_by('-quantity').first()
    return row.location_id if row else None


@login_required
def order(request, pk):
    item = get_object_or_404(Order.objects.select_related('vendor', 'created_by', 'ask'), pk=pk)
    form = OrderForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'{item} is saved.')
        return redirect(item)
    lines = list(item.lines.select_related('part', 'asset'))
    left = None   # what the budget has left once this draft is placed
    if item.budget_id and item.status == Order.Status.DRAFT:
        from budgets.money import totals
        left = totals([item.budget])[item.budget_id].remaining - item.total
    return render(request, 'orders/order.html', {
        'budget_left': left,
        'order': item, 'form': form, 'lines': [(line, _where(line)) for line in lines], 'locations': Location.ordered(),
        'today': date.today(), 'categories': Category.of(Category.Kind.PARTS),
        'assets_json': [{'number': a.number, 'description': a.name, 'category': a.get_kind_display(), 'have': '', 'asset': True,
                         'price': qty(a.price)} for a in Asset.objects.filter(status=Asset.Status.ORDERED, order_lines=None)]})


def _draft(request, pk):
    item = get_object_or_404(Order, pk=pk)
    if item.status != Order.Status.DRAFT:
        raise ValidationError(f'{item} is {item.get_status_display().lower()}: its lines can\'t change any more.')
    return item


@login_required
@require_POST
def line_add(request, pk):
    try:
        item = _draft(request, pk)
        number = request.POST.get('part', '').strip()
        part = Part.objects.filter(number__iexact=number).first()
        asset = Asset.objects.filter(number__iexact=number).first() if part is None else None
        if asset is not None:   # an asset on order, by its asset tag
            if asset.status != Asset.Status.ORDERED or asset.order_lines.exclude(order__status=Order.Status.CANCELLED).exists():
                raise ValidationError(f'{asset} is not an asset waiting to be ordered.')
            OrderLine.objects.create(order=item, asset=asset, quantity=1, price=asset.price)
            return redirect(reverse('orders:order', args=[pk]) + '#add')
        if part is None:
            raise ValidationError(f'There is no part or asset "{number}".')
        quantity = stock.amount(request.POST.get('quantity'))
        price = request.POST.get('price', '').strip()
        line = item.lines.filter(part=part).first()
        if line:
            line.quantity += quantity
            line.save(update_fields=['quantity'])
        else:
            OrderLine.objects.create(order=item, part=part, quantity=quantity,
                                     price=stock.amount(price, allow_zero=True) if price else part.price)
    except ValidationError as exc:
        errors(request, exc)
    return redirect(reverse('orders:order', args=[pk]) + '#add')   # the popup opens again, for the next one


@login_required
@require_POST
def line_change(request, pk, line):
    try:
        item = _draft(request, pk)
        row = get_object_or_404(OrderLine, pk=line, order=item)
        if request.POST.get('remove'):
            row.delete()
        else:
            row.quantity = Decimal(1) if row.asset_id else stock.amount(request.POST.get('quantity'))
            price = request.POST.get('price', '').strip()
            row.price = stock.amount(price, allow_zero=True) if price else None
            row.save(update_fields=['quantity', 'price'])
    except ValidationError as exc:
        errors(request, exc)
    return redirect('orders:order', pk)


@login_required
@require_POST
def place(request, pk):
    item = get_object_or_404(Order, pk=pk)
    expected = request.POST.get('expected_on')
    try:
        service.place(item, request.user, date.fromisoformat(expected) if expected else None)
        messages.success(request, f'{item} is placed with {item.vendor}.')
    except (ValidationError, ValueError) as exc:
        errors(request, exc if isinstance(exc, ValidationError) else ValidationError('That is not a date.'))
    return redirect(item)


@login_required
@require_POST
def receive(request, pk):
    item = get_object_or_404(Order, pk=pk)
    locations = {loc.pk: loc for loc in Location.objects.all()}
    arrived = []
    for line in item.lines.select_related('part'):
        quantity = request.POST.get(f'q_{line.pk}', '').strip()
        if quantity and quantity != '0':
            where = request.POST.get(f'l_{line.pk}', '')
            arrived.append((line, quantity, locations.get(int(where)) if where.isdigit() else None))
    try:
        booked = service.receive(item, arrived, request.user)
        messages.success(request, f'Received: {", ".join(booked)}.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)


@login_required
@require_POST
def cancel(request, pk):
    item = get_object_or_404(Order, pk=pk)
    try:
        service.cancel(item, request.user)
        messages.success(request, f'{item} is cancelled.')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(item)
