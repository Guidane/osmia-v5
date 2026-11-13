"""Parts (finding them, their page with stock, history and orders), locations, vendors and categories."""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
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
from .forms import AttributeForm, BranchForm, CategoryForm, FamilyBranchForm, FamilyForm, LocationForm, PartForm, VendorForm
from .models import Attribute, Branch, Category, Family, FamilyBranch, Location, Part, PartLink, PartValue, Stock, Vendor

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
    tree = Category.of(Category.Kind.PARTS)
    own = dict(Part.objects.filter(active=True).values('category').annotate(n=Count('pk')).values_list('category', 'n'))
    children = {}
    for c, _ in tree:
        children.setdefault(c.parent_id, []).append(c.pk)

    def counted(pk):   # its parts and those of the categories under it
        return own.get(pk, 0) + sum(counted(child) for child in children.get(pk, []))
    picked = Part.objects.filter(pk=request.GET.get('part') or 0).first()
    return render(request, 'inventory/parts.html', {
        'rows': attributes_kept.columns(list(found[:PAGE]), attributes, PartStore()), 'count': found.count(), 'q': q,
        'category': category, 'categories': [(c, depth, counted(c.pk)) for c, depth in tree], 'page': PAGE,
        'attributes': attributes, 'filters': attributes_kept.filters(attributes, request.GET),
        'every': Part.objects.filter(active=True).count(), 'open': set(category.chain_pks()) if category else set(),
        'picked': picked, 'brief': _brief(picked) if picked else None})


def _brief(part):
    """What the details beside the parts list show of ``part``."""
    return {'part': part, 'attributes': attributes_kept.shown(part, part.category),
            'stock': part.stock.select_related('location').filter(quantity__gt=0), 'on_hand': part.on_hand,
            'on_order': orders.on_order(part)}


@login_required
def part_brief(request, pk):
    """The details of a part beside the parts list (fetched when one is picked)."""
    part = get_object_or_404(Part.objects.select_related('category', 'vendor', 'family', 'branch'), pk=pk)
    return render(request, 'inventory/_part_brief.html', _brief(part))


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
    part = get_object_or_404(Part.objects.select_related('category', 'vendor', 'family', 'branch'), pk=pk)
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
    """The locations, like the parts: their tree on the left, what is kept at the one picked (and in those inside it:
    parts in stock, assets) in the middle; on the right the details of the part or asset picked, else the location's own:
    its picture, its files and its documentation."""
    from assets.models import Asset
    from assets.views import _brief as asset_brief
    from web import briefs, browse
    place = Location.objects.filter(pk=request.GET.get('location') or 0).first()
    q = request.GET.get('q', '').strip()
    stock = Stock.objects.filter(quantity__gt=0).select_related('part', 'location')
    kept_here = Asset.objects.exclude(location=None).exclude(status=Asset.Status.RETIRED).select_related('location')
    if place is not None:
        stock, kept_here = stock.filter(location_id__in=place.below()), kept_here.filter(location_id__in=place.below())
    if q:
        stock = stock.filter(Q(part__number__icontains=q) | Q(part__description__icontains=q))
        kept_here = kept_here.filter(Q(number__icontains=q) | Q(name__icontains=q))
    own = dict(Stock.objects.filter(quantity__gt=0).values('location').annotate(n=Count('pk')).values_list('location', 'n'))
    for pk, n in Asset.objects.exclude(location=None).exclude(status=Asset.Status.RETIRED).values('location').annotate(n=Count('pk')).values_list('location', 'n'):
        own[pk] = own.get(pk, 0) + n
    keep = browse.keep(request, 'q')
    tree = Location.ordered()
    nodes = [browse.node('All locations', f'?{keep[1:]}', sum(own.values()), place is None)] + browse.nodes(
        tree, own, place, lambda l: f'?location={l.pk}{keep}', label=lambda l: l.name, thumbs=True)
    wanted = request.GET.get('part', '')   # the row picked: a part, or (a<id>) an asset
    part = Part.objects.filter(pk=wanted).first() if wanted.isdigit() else None
    asset = Asset.objects.filter(pk=wanted[1:]).first() if wanted[:1] == 'a' and wanted[1:].isdigit() else None
    return render(request, 'inventory/locations.html', {
        'nodes': nodes, 'place': place, 'q': q, 'stock': stock[:500], 'assets': kept_here[:200], 'wanted': wanted,
        'locations': [(node, depth, own.get(node.pk, 0)) for node, depth in tree],
        'part_brief': _brief(part) if part else None, 'asset_brief': asset_brief(asset) if asset else None,
        # the location itself: its picture, files and pages
        'brief': briefs.of('location', place) if place and not part and not asset else None})


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
    """The vendors: those dealt with and those no longer on the left, the vendors in the middle, the details of the
    one picked on the right."""
    from web import briefs, browse
    shown = request.GET.get('show', '')
    q = request.GET.get('q', '').strip()
    found = Vendor.objects.all()
    if shown in ('active', 'inactive'):
        found = found.filter(active=shown == 'active')
    if q:
        found = found.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(email__icontains=q))
    kept = browse.keep(request, 'q')
    nodes = [browse.node('All vendors', f'?{kept[1:]}', Vendor.objects.count(), not shown),
             browse.node('Active', f'?show=active{kept}', Vendor.objects.filter(active=True).count(), shown == 'active'),
             browse.node('Inactive', f'?show=inactive{kept}', Vendor.objects.filter(active=False).count(), shown == 'inactive')]
    picked = Vendor.objects.filter(pk=request.GET.get('vendor') or 0).first()
    return render(request, 'inventory/vendors.html', {'vendors': found, 'nodes': nodes, 'q': q, 'shown': shown, 'picked': picked,
                                                      'brief': briefs.of('vendor', picked) if picked else None})


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
    """The connector families, like the parts: their branches as a tree on the left (D-sub, Circular / M12, …), the
    families of the one picked in the middle, the details of the family picked on the right. A family or a branch is
    made or changed on a form of its own (?new=family, ?new=branch, ?edit=<family>, ?branch=<branch>)."""
    from .faces import natural
    item = Family.objects.filter(pk=request.GET.get('edit') or 0).first()
    branch = FamilyBranch.objects.filter(pk=request.GET.get('branch') or 0).first()
    making = request.POST.get('form') or ('family' if item or request.GET.get('new') == 'family' else
                                          'branch' if branch or request.GET.get('new') == 'branch' else '')
    group = FamilyBranch.objects.filter(pk=request.GET.get('group') or 0).first()
    if making:
        start = {'group': group.pk} if group and not item else {}
        under = {'parent': group.pk} if group and not branch else {}
        form = FamilyForm(request.POST if making == 'family' and request.method == 'POST' else None, instance=item, prefix='family', initial=start)
        branch_form = FamilyBranchForm(request.POST if making == 'branch' and request.method == 'POST' else None, instance=branch,
                                       prefix='branch', initial=under)
        sent = branch_form if making == 'branch' else form
        if sent.is_bound and sent.is_valid():
            saved = sent.save()
            messages.success(request, f'{saved} is saved.')
            where = saved.group_id if making == 'family' else saved.pk
            return redirect(reverse('inventory:families') + (f'?group={where}' if where else '')
                            + (f'{"&" if where else "?"}family={saved.pk}' if making == 'family' else ''))
        title = (f'Change {item.name}' if item else 'New connector family') if making == 'family' else \
                (f'Change {branch.name}' if branch else 'New branch')
        return render(request, 'inventory/family_form.html', {'form': sent, 'kind': making, 'title': title,
                                                              'back': reverse('inventory:families') + (f'?group={group.pk}' if group else '')})
    q = request.GET.get('q', '').strip()
    every = sorted(Family.objects.annotate(n=Count('parts')).select_related('group').prefetch_related('branches'), key=lambda f: natural(f.name))
    found = [f for f in every if (not q or q.lower() in f.name.lower()) and (group is None or f.group_id in group.below())]
    tree = FamilyBranch.ordered()
    own, children = {}, {}
    for f in every:
        own[f.group_id] = own.get(f.group_id, 0) + 1
    for b, _ in tree:
        children.setdefault(b.parent_id, []).append(b.pk)

    def counted(pk):   # its families and those of the branches under it
        return own.get(pk, 0) + sum(counted(child) for child in children.get(pk, []))
    keep = f'&q={q}' if q else ''
    open_ = set(group.chain_pks()) if group else set()
    nodes = [{'label': 'All families', 'url': f'?{keep[1:]}', 'count': len(every), 'on': group is None}] + [
        {'label': b.name, 'url': f'?group={b.pk}{keep}', 'depth': depth, 'count': counted(b.pk), 'on': group == b, 'open': b.pk in open_}
        for b, depth in tree]
    picked = Family.objects.filter(pk=request.GET.get('family') or 0).first()
    return render(request, 'inventory/families.html', {'families': found, 'nodes': nodes, 'group': group, 'q': q, 'picked': picked,
                                                       'brief': _family_brief(picked) if picked else None})


def _family_brief(family):
    """What the details beside the list of connector families show of ``family``."""
    face = family.face if (family.face or {}).get('contacts') else None
    return {'family': family, 'face': {'face': face, 'pins': [[c[0], ''] for c in face['contacts']]} if face else None,
            'branches': family.branches.annotate(n=Count('parts')),
            'parts': family.parts.select_related('branch').annotate(have=Sum('stock__quantity'))[:30]}


@login_required
def family_brief(request, pk):
    """The details of a connector family beside their list (fetched when one is picked)."""
    return render(request, 'inventory/_family_brief.html', _family_brief(get_object_or_404(Family.objects.select_related('group'), pk=pk)))


@login_required
@require_POST
def standard_families(request):
    """The connectors made often (D-sub, D-sub HD, Gecko) as families, those not there yet."""
    from .faces import standard_families as make
    made = make()
    messages.success(request, f'{made} standard connector famil{"y" if made == 1 else "ies"} added.' if made else
                     'The standard connector families are all there.')
    return redirect('inventory:families')


@login_required
def family(request, pk):
    """A family: its branches (added, or renamed: ?branch=<pk>), its parts, their stock together, the one it is
    ordered as."""
    item = get_object_or_404(Family, pk=pk)
    branch = item.branches.filter(pk=request.GET.get('branch') or 0).first()
    form = BranchForm(request.POST or None, instance=branch, family=item)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved} is saved.')
        return redirect(item)
    from .faces import mirrored
    face = item.face if (item.face or {}).get('contacts') else None
    return render(request, 'inventory/family.html', {
        'faces': {side: {'face': f, 'pins': [[c[0], ''] for c in f['contacts']]} for side, f in (('pin', face), ('socket', mirrored(face)))}
                 if face else None,
        'family': item, 'form': form, 'branch': branch, 'branches': item.branches.annotate(n=Count('parts')),
        'parts': item.parts.select_related('vendor', 'branch').annotate(have=Sum('stock__quantity'))})


def _with_branches(family):
    """A connector family has a pin branch and a socket branch (made when missing; a branch named so is marked so)."""
    for contacts, name in (('pin', 'pin'), ('socket', 'socket')):
        if family.branches.filter(contacts=contacts).exists():
            continue
        named = family.branches.filter(name__iexact=name).first()
        if named:
            named.contacts = contacts
            named.save(update_fields=['contacts'])
        else:
            Branch.objects.create(family=family, name=name, contacts=contacts)


def _face_sent(text):
    """The face sent by the connector editor, checked and fitted; ValidationError when it isn't right."""
    from .faces import SHAPES, fitted
    try:
        data = json.loads(text or '')
        shape = data['shape'] if data['shape'] in dict(SHAPES) else 'rect'
        contacts = [[str(n).strip(), float(x), float(y)] for n, x, y in data['contacts']]
        outline = [[float(x), float(y)] for x, y in data.get('outline') or []] if shape == 'custom' else None
    except (ValueError, TypeError, KeyError):
        raise ValidationError('The connector could not be read.')
    if shape == 'custom' and len(outline) < 3:
        raise ValidationError('An outline of its own needs at least 3 corners.')
    numbers = [c[0] for c in contacts]
    if '' in numbers:
        raise ValidationError('Every contact needs a number.')
    twice = sorted({n for n in numbers if numbers.count(n) > 1})
    if twice:
        raise ValidationError(f'Contact {", ".join(twice)} is there twice.')
    return fitted(shape, contacts, outline)


@login_required
def connector(request, pk):
    """The connector editor of a family: its outline and its contacts (where each sits, its number), as seen from the
    pin side; made from a ready-made one, or changed by hand. Its pin and socket branches are made with it."""
    from .faces import SHAPES, STARTS, preset, preset_choices, start
    item = get_object_or_404(Family, pk=pk)
    if request.method == 'POST':
        try:
            if request.POST.get('action') == 'start':
                face = preset(request.POST.get('kind')) or start(request.POST.get('kind'), min(int(request.POST.get('positions') or 1), 200),
                                                                 int(request.POST.get('columns') or 0) or None)
            else:
                face = _face_sent(request.POST.get('face'))
        except ValueError:
            messages.error(request, 'Positions and columns are numbers.')
            return redirect('inventory:connector', pk=item.pk)
        except ValidationError as exc:
            errors(request, exc)
            return redirect('inventory:connector', pk=item.pk)
        if request.POST.get('action') != 'start' and (item.face or {}).get('genders') is False:
            face['genders'] = False   # a ring terminal changed by hand: still without sides
        with transaction.atomic():
            item.face = face
            item.save(update_fields=['face'])
            if face.get('genders', True):
                _with_branches(item)
        messages.success(request, f'The {item} connector is saved.')
        return redirect('inventory:connector' if request.POST.get('action') == 'start' else 'inventory:family', pk=item.pk)
    return render(request, 'inventory/connector.html', {'family': item, 'face': item.face or {'shape': 'rect', 'contacts': []},
                                                        'shapes': SHAPES, 'starts': STARTS, 'presets': preset_choices()})


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
