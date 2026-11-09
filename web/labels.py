"""Labels (stickers) for parts and assets, printed on A4 sheets of labels: one or many at a time, in the sheet size and
with what each label shows chosen on the page (and kept as the default for parts or assets).

/labels/part/?ids=3,8,12 (or /labels/asset/…): the sheets, ready to print."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from .models import LabelLayout

# name, label width × height (mm), columns × rows, top and left margin, gap across and down (mm)
SIZES = {
    '38x21': ('38.1 × 21.2 mm, 65 a sheet', 38.1, 21.2, 5, 13, 10.7, 4.7, 2.5, 0),
    '48x25': ('48.5 × 25.4 mm, 40 a sheet', 48.5, 25.4, 4, 10, 21.5, 8.0, 0, 0),
    '64x38': ('63.5 × 38.1 mm, 21 a sheet', 63.5, 38.1, 3, 7, 15.15, 7.2, 2.5, 0),
    '99x38': ('99.1 × 38.1 mm, 14 a sheet', 99.1, 38.1, 2, 7, 15.15, 4.65, 2.5, 0),
    '105x74': ('105 × 74 mm, 8 a sheet', 105.0, 74.0, 2, 4, 0, 0, 0, 0),
}
SHOWN = {   # what a label can show, with what it shows by default
    'part': [('number', 'Part number', True), ('description', 'Description', True), ('picture', 'Picture', False),
             ('category', 'Category', False), ('location', 'Where it is kept', False)],
    'asset': [('number', 'Asset tag', True), ('name', 'Name', True), ('picture', 'Picture', False), ('serial', 'Serial number', False),
              ('category', 'Category', False), ('location', 'Where it is kept', False)],
}


def _things(kind, ids):
    if kind == 'part':
        from inventory.models import Part
        model = Part
    else:
        from assets.models import Asset
        model = Asset
    found = {o.pk: o for o in model.objects.filter(pk__in=ids).select_related('category')}
    return [found[i] for i in ids if i in found]


def _layout(kind, query):
    """What the labels show: from the page's choices when given, else the saved default, else the first defaults."""
    saved = LabelLayout.objects.filter(kind=kind).first()
    base = saved.data if saved else {'size': '64x38', 'show': [k for k, _, on in SHOWN[kind] if on], 'attributes': []}
    if 'size' not in query:
        return base
    return {'size': query.get('size') if query.get('size') in SIZES else base['size'],
            'show': [k for k, _, _ in SHOWN[kind] if query.get(f'show_{k}')], 'attributes': query.getlist('attribute')}


def _label(kind, thing, layout, attributes):
    """What one label shows: [(class, text)] lines, and the picture's address (or '')."""
    from inventory.attributes import columns, store_for

    from .things import preview_of
    show = layout['show']
    lines = []
    if 'number' in show:
        lines.append(('number', thing.number))
    text = thing.description if kind == 'part' else thing.name
    if ('description' in show or 'name' in show) and text:
        lines.append(('text', text))
    if 'serial' in show and getattr(thing, 'serial', ''):
        lines.append(('small', f'S/N {thing.serial}'))
    if 'category' in show and thing.category:
        lines.append(('small', thing.category.name))
    if 'location' in show:
        where = thing.location if kind == 'asset' else next((s.location for s in thing.stock.filter(quantity__gt=0).select_related('location')), None)
        if where:
            lines.append(('small', where.path))
    wanted = [a for a in attributes if a.name in layout['attributes']]
    if wanted:
        _, values = columns([thing], wanted, store_for(thing))[0]
        lines += [('small', f'{a.name}: {v}') for a, v in zip(wanted, values) if v]
    picture = ''
    if 'picture' in show:
        shown = preview_of(thing)
        if shown is not None:
            picture = reverse('web:file', args=[shown.pk])
    return lines, picture


@login_required
def sheet(request, kind):
    if kind not in SHOWN:
        raise Http404
    ids = [int(i) for i in request.GET.get('ids', '').replace(' ', '').split(',') if i.isdigit()]
    things = _things(kind, ids)
    layout = _layout(kind, request.GET)
    if request.GET.get('save'):
        LabelLayout.objects.update_or_create(kind=kind, defaults={'data': layout})
        messages.success(request, f'This is how labels of {kind}s look from now on.')
        query = request.GET.copy()
        query.pop('save')
        return redirect(f'{request.path}?{query.urlencode()}')
    attributes = {}   # the attributes of the things' categories, to choose from
    for thing in things:
        for a in thing.category.all_attributes() if thing.category else []:
            if not a.is_link:
                attributes.setdefault(a.name, a)
    copies = max(1, min(int(request.GET.get('copies') or 1), 100)) if str(request.GET.get('copies') or '1').isdigit() else 1
    skip = min(int(request.GET.get('skip') or 0), 200) if str(request.GET.get('skip') or '0').isdigit() else 0
    labels = [None] * skip + [_label(kind, t, layout, list(attributes.values())) for t in things for _ in range(copies)]
    name, width, height, cols, rows, top, left, gap_x, gap_y = SIZES[layout['size']]
    per_page = cols * rows
    pages = [labels[i:i + per_page] for i in range(0, len(labels), per_page)] or [[]]
    return render(request, 'web/labels.html', {
        'kind': kind, 'things': things, 'ids': ','.join(str(t.pk) for t in things), 'layout': layout, 'pages': pages,
        'sizes': [(k, v[0]) for k, v in SIZES.items()], 'shown': SHOWN[kind], 'attributes': list(attributes),
        'copies': copies, 'skip': skip, 'sheet': {'width': width, 'height': height, 'cols': cols, 'top': top, 'left': left,
                                                  'gap_x': gap_x, 'gap_y': gap_y}})
