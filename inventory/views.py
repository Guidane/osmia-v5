"""Parts (finding them, their page with stock, history and orders), locations, vendors and categories."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from orders import service as orders
from web import excel
from web.templatetags.osmia import qty
from web.shortcuts import edit_page, errors
from web.forms import initial_for

from . import attributes as attributes_kept
from . import stock
from .attributes import PartStore
from .forms import AttributeForm, CategoryForm, FamilyForm, LocationForm, PartForm, VendorForm
from .models import Attribute, Category, Family, Location, Part, PartLink, PartValue, Stock, Vendor

PAGE = 200   # parts listed at most



def search(found, q):
    """Parts with every word of ``q`` in their number, description, manufacturer or numbers."""
    for word in q.split():
        found = found.filter(Q(number__icontains=word) | Q(description__icontains=word) | Q(manufacturer__icontains=word)
                             | Q(mpn__icontains=word) | Q(vendor_number__icontains=word))
    return found


@login_required
def find(request):
    """Parts matching ?q= (words) and ?category= (with those under it), for finding one to pick: JSON."""
    found = search(Part.objects.filter(active=True).select_related('category').annotate(have=Sum('stock__quantity')),
                   request.GET.get('q', '').strip())
    category = Category.objects.filter(pk=request.GET.get('category') or 0).first()
    if category is not None:
        found = found.filter(category_id__in=category.below())
    return JsonResponse({'parts': [{'number': p.number, 'description': p.description, 'category': p.category.name if p.category else '',
                                    'have': qty(p.have or 0), 'unit': p.get_unit_display(), 'price': qty(p.price)}
                                   for p in found[:60]], 'more': found.count() > 60})


@login_required
def parts(request):
    q = request.GET.get('q', '').strip()
    found = search(Part.objects.select_related('category', 'vendor').annotate(have=Sum('stock__quantity')), q)
    category = Category.objects.filter(pk=request.GET.get('category') or 0).first()
    attributes = category.all_attributes() if category else []
    if category is not None:
        found = attributes_kept.filtered(found.filter(category_id__in=category.below()), attributes, request.GET, PartStore())
    if not request.GET.get('all'):
        found = found.filter(active=True)
    if request.GET.get('export'):
        return excel.download('parts', _part_sheets(found))
    if q and found.count() == 1:
        return redirect(found.get())
    return render(request, 'inventory/parts.html', {
        'rows': attributes_kept.columns(list(found[:PAGE]), attributes, PartStore()), 'count': found.count(), 'q': q,
        'category': category, 'categories': Category.of(Category.Kind.PARTS), 'page': PAGE, 'attributes': attributes,
        'filters': attributes_kept.filters(attributes, request.GET)})


def _part_sheets(parts):
    parts = list(parts)
    return [('Parts', ['Part number', 'Description', 'Category', 'Manufacturer', 'Manufacturer part number', 'Unit', 'Vendor',
                       "Vendor's number", 'Last price', 'Minimum', 'On hand', 'Active'],
             [(p.number, p.description, p.category.path if p.category else '', p.manufacturer, p.mpn, p.unit,
               p.vendor.name if p.vendor else '', p.vendor_number, p.price, p.minimum, p.have or 0, 'yes' if p.active else 'no') for p in parts]),
            ('Stock', ['Part number', 'Location', 'Quantity'],
             [(s.part.number, s.location.path, s.quantity) for s in Stock.objects.filter(part__in=parts, quantity__gt=0)
              .select_related('part', 'location')]),
            ('Attributes', ['Part number', 'Category', 'Attribute', 'Value', 'Unit'],
             [(v.part.number, v.part.category.path if v.part.category else '', v.attribute.name,
               v.number if v.number is not None else v.value, v.attribute.unit)
              for v in PartValue.objects.filter(part__in=parts).select_related('part__category', 'attribute')]
             + [(link.part.number, link.part.category.path if link.part.category else '', link.attribute.name, link.target.number, '')
                for link in PartLink.objects.filter(part__in=parts).select_related('part__category', 'attribute', 'target')])]


@login_required
def part_form(request, pk=None):
    part = get_object_or_404(Part, pk=pk) if pk else None
    form = PartForm(request.POST or None, instance=part, initial=initial_for(part, category=request.GET.get('category')))
    if request.method == 'POST' and not request.POST.get('refresh') and form.is_valid():   # refresh: its category changed
        part = form.save()
        messages.success(request, f'{part} is saved.')
        return redirect(part)
    numbers = Part.objects.filter(active=True).values_list('number', 'description')[:5000] \
        if any(a.kind == Attribute.Kind.LINK and not a.to_assets for a in form.attributes) else []
    return render(request, 'inventory/attributes_form.html', {'form': form, 'title': f'Change {part}' if part else 'New part',
                                                              'back': part.get_absolute_url() if part else None, 'part_numbers': numbers})


@login_required
def part(request, pk):
    part = get_object_or_404(Part.objects.select_related('category', 'vendor'), pk=pk)
    return render(request, 'inventory/part.html', {
        'attributes': attributes_kept.shown(part, part.category), 'linked_here': attributes_kept.linked_here(part),
        'part': part, 'stock': part.stock.select_related('location').filter(quantity__gt=0),
        'on_hand': part.on_hand, 'on_order': orders.on_order(part),
        'lines': part.order_lines.select_related('order__vendor').order_by('-order__pk')[:20],
        'movements': part.movements.select_related('source', 'target', 'user')[:50],
        'locations': Location.ordered()})


@login_required
@require_POST
def part_stock(request, pk):
    """Add, move, use or count stock of a part, from its page."""
    part = get_object_or_404(Part, pk=pk)
    post = request.POST
    where = Location.objects.filter(pk=post.get('location') or 0).first()
    to = Location.objects.filter(pk=post.get('to') or 0).first()
    action, note = post.get('action'), post.get('note', '')
    try:
        if where is None or (action == 'move' and to is None):
            raise ValidationError('Pick the location.')
        if action == 'add':
            stock.add(part, post.get('quantity'), where, request.user, note)
        elif action == 'move':
            stock.move(part, post.get('quantity'), where, to, request.user, note)
        elif action == 'use':
            stock.use(part, post.get('quantity'), where, request.user, note)
        elif action == 'count':
            stock.count(part, where, post.get('quantity'), request.user, note)
        else:
            raise ValidationError('What should happen to the stock?')
    except ValidationError as exc:
        errors(request, exc)
    return redirect(part)


@login_required
@require_POST
def part_reorder(request, pk):
    part = get_object_or_404(Part, pk=pk)
    try:
        line = orders.reorder(part, request.user)
    except ValidationError as exc:
        errors(request, exc)
        return redirect(part)
    messages.success(request, f'{line.quantity.normalize():f} × {part} is on {line.order} ({line.order.vendor}).')
    return redirect(line.order)


@login_required
def locations(request):
    totals = dict(Stock.objects.filter(quantity__gt=0).values('location').annotate(n=Sum('quantity')).values_list('location', 'n'))
    kinds = dict(Stock.objects.filter(quantity__gt=0).values('location').annotate(n=Count('pk')).values_list('location', 'n'))
    return render(request, 'inventory/locations.html', {
        'locations': [(node, depth, kinds.get(node.pk, 0)) for node, depth in Location.ordered()], 'totals': totals})


@login_required
def location(request, pk):
    place = get_object_or_404(Location, pk=pk)
    here = Stock.objects.filter(location_id__in=place.below(), quantity__gt=0).select_related('part', 'location')
    if request.GET.get('export'):
        return excel.download(place.path, [('Stock', ['Part number', 'Description', 'Location', 'Quantity', 'Unit'],
                                            [(s.part.number, s.part.description, s.location.path, s.quantity, s.part.unit) for s in here])])
    return render(request, 'inventory/location.html', {'location': place, 'stock': here, 'children': place.children.all()})


@login_required
def location_form(request, pk=None):
    place = get_object_or_404(Location, pk=pk) if pk else None
    return edit_page(request, LocationForm(request.POST or None, instance=place, initial=initial_for(place, parent=request.GET.get('parent'))),
                     'location')


@login_required
def vendors(request):
    return render(request, 'inventory/vendors.html', {'vendors': Vendor.objects.all()})


@login_required
def vendor(request, pk):
    item = get_object_or_404(Vendor, pk=pk)
    return render(request, 'inventory/vendor.html', {'vendor': item, 'parts': item.parts.filter(active=True),
                                                     'orders': item.orders.all()[:30]})


@login_required
def vendor_form(request, pk=None):
    item = get_object_or_404(Vendor, pk=pk) if pk else None
    return edit_page(request, VendorForm(request.POST or None, instance=item), 'vendor')


@login_required
def families(request):
    """The families of parts that can take each other's place, with a form to make one."""
    form = FamilyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        return redirect(form.save())
    return render(request, 'inventory/families.html', {'families': Family.objects.annotate(n=Count('parts')).select_related('preferred'),
                                                       'form': form})


@login_required
def family(request, pk):
    """A family: its parts (their stock together), the one it is ordered as, and changing it."""
    item = get_object_or_404(Family, pk=pk)
    form = FamilyForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'{item} is saved.')
        return redirect(item)
    return render(request, 'inventory/family.html', {
        'family': item, 'form': form, 'parts': item.parts.select_related('vendor').annotate(have=Sum('stock__quantity'))})


@login_required
def categories(request):
    """The categories of parts (or of assets: ?kind=assets) as a tree, with a form to add one (or change one: ?edit=<pk>)."""
    from assets.models import Asset
    item = Category.objects.filter(pk=request.GET.get('edit') or 0).first()
    kind = item.kind if item else request.GET.get('kind') if request.GET.get('kind') in Category.Kind.values else Category.Kind.PARTS
    form = CategoryForm(request.POST or None, instance=item, kind=kind)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved} is saved.')
        return redirect(f"{reverse('inventory:categories')}?kind={kind}")
    if kind == Category.Kind.ASSETS:
        counts = Asset.objects.exclude(status='retired')
    else:
        counts = Part.objects.filter(active=True)
    counts = dict(counts.values('category').annotate(n=Count('pk')).values_list('category', 'n'))
    own = dict(Attribute.objects.values('category').annotate(n=Count('pk')).values_list('category', 'n'))
    return render(request, 'inventory/categories.html', {
        'categories': [(c, depth, counts.get(c.pk, 0), own.get(c.pk, 0)) for c, depth in Category.of(kind)], 'form': form, 'item': item,
        'kind': kind, 'kinds': Category.Kind.choices})


def _category_page(request, item, form):
    """A category's page: the attributes its parts and assets fill in (those it gets from above, and its own), the
    categories under it, how many parts and assets are in it, and a form to add an attribute."""
    from assets.models import Asset
    every = item.all_attributes()
    below = item.below()
    return render(request, 'inventory/category.html', {
        'category': item, 'inherited': [a for a in every if a.category_id != item.pk], 'own': [a for a in every if a.category_id == item.pk],
        'form': form, 'children': item.children.all(), 'parts': Part.objects.filter(category_id__in=below, active=True).count(),
        'assets': Asset.objects.filter(category_id__in=below).exclude(status='retired').count()})


@login_required
def category(request, pk):
    item = get_object_or_404(Category, pk=pk)
    return _category_page(request, item, AttributeForm(category=item))


@login_required
def attribute_form(request, pk, attribute=None):
    item = get_object_or_404(Category, pk=pk)
    current = get_object_or_404(Attribute, pk=attribute, category=item) if attribute else None
    form = AttributeForm(request.POST or None, instance=current, category=item)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved.name} is saved.')
        return redirect(f'{item.get_absolute_url()}#attributes')
    if current is None:   # adding happens on the category's page
        return _category_page(request, item, form)
    return render(request, 'web/form.html', {'form': form, 'title': f'{current.name} of {item.name}', 'back': item.get_absolute_url()})


@login_required
@require_POST
def attribute_delete(request, pk, attribute):
    item = get_object_or_404(Category, pk=pk)
    found = get_object_or_404(Attribute, pk=attribute, category=item)
    found.delete()
    messages.success(request, f'{found.name} is taken away, with what was filled in for it.')
    return redirect(f'{item.get_absolute_url()}#attributes')


@login_required
@require_POST
def attribute_move(request, pk, attribute):
    """Move an attribute up or down among its category's."""
    item = get_object_or_404(Category, pk=pk)
    order = list(item.attributes.all())
    found = get_object_or_404(Attribute, pk=attribute, category=item)
    i = order.index(found)
    j = i - 1 if request.POST.get('to') == 'up' else i + 1
    if 0 <= j < len(order):
        order[i], order[j] = order[j], order[i]
        for position, a in enumerate(order):
            Attribute.objects.filter(pk=a.pk).update(position=position)
    return redirect(f'{item.get_absolute_url()}#attributes')
