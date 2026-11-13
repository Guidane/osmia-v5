"""The details beside a list (the right pane of a list with a tree: ``web/static/web/browser.js``) of the kinds of thing
that haven't a pane of their own: what ``web/_brief.html`` shows of one: its title and badges, a line of what it is,
its details ([(label, text, link)]) and small tables ([(heading, rows, empty)]; a cell: text or (text, link))."""
from django.http import Http404
from django.urls import reverse

from .templatetags.osmia import money, qty


def _cells(rows):
    return [[{'text': c[0], 'url': c[1]} if isinstance(c, tuple) else {'text': c, 'url': ''} for c in row] for row in rows]


def _table(heading, rows, empty='None.'):
    return (heading, _cells(rows), empty)


def _link(obj):
    return (str(obj), obj.get_absolute_url()) if obj is not None else ''


def _date(value):
    from django.utils.formats import date_format
    return date_format(value, 'j M Y') if value else ''


def device(d):
    connectors = [((c.designator, f'{d.get_absolute_url()}#c{c.pk}'), c.name, c.used_name, f'{c.pins.count()} pins')
                  for c in d.connectors.select_related('part', 'family', 'branch')]
    return {'badges': [('Bought', '')] if d.origin == 'external' else [], 'what': d.name,
            'edit_url': reverse('devices:edit', args=[d.pk]), 'title': d.number,
            'details': [('Made', d.get_origin_display(), ''), ('Manufacturer', ' · '.join(x for x in (d.manufacturer, d.model) if x), ''),
                        ('Version', f'v{d.version}' if d.version else 'not saved', ''), ('Description', d.description, '')],
            'tables': [_table('Connectors', connectors, 'No connectors yet.'),
                       _table('Assets', [(_link(a), a.get_status_display()) for a in d.assets.all()[:20]])]}


def order(o):
    lines = [(_link(line.item) if hasattr(line.item, 'get_absolute_url') else line.item.number,
              f'{qty(line.quantity)}', f'{qty(line.received)} in', money(line.price)) for line in o.lines.select_related('part', 'asset')]
    late = o.overdue
    return {'title': o.number, 'what': str(o.vendor or ''),
            'badges': [('Late' if late else o.get_status_display(), 'ok' if o.status == 'received' else 'failed' if late or o.status == 'cancelled' else '')],
            'details': [('Asked for', o.request, ''), ('Budget', str(o.budget or ''), o.budget.get_absolute_url() if o.budget else ''),
                        ('Project', str(o.in_project or ''), o.in_project.get_absolute_url() if o.in_project else ''),
                        ("Vendor's number", o.vendor_reference, ''), ('Ordered', _date(o.ordered_on), ''),
                        ('Expected', _date(o.expected_on), ''), ('Received', _date(o.received_on), ''), ('By', str(o.created_by or ''), '')],
            'tables': [_table('Lines', lines, 'No lines yet.')]}


def diagram(p):
    from projects.models import Configuration
    configurations = [((c.name, c.get_absolute_url()), c.description[:60]) for c, _ in Configuration.ordered(p.configurations.all())]
    return {'title': str(p), 'what': p.description, 'edit_url': reverse('projects:edit', args=[p.pk]),
            'details': [('Project', str(p.in_project or ''), p.in_project.get_absolute_url() if p.in_project else ''),
                        ('Owner', str(p.owner or ''), ''), ('Department', str(p.department or ''), '')],
            'tables': [_table('Configurations', configurations),
                       _table('Harnesses', [((h.number, h.get_absolute_url()), h.name, h.get_status_display()) for h in p.harnesses.all()])]}


def project(p):
    return {'title': str(p), 'what': p.description, 'edit_url': reverse('work:edit', args=[p.pk]),
            'badges': [(p.get_status_display(), 'ok' if p.status == 'active' else '')],
            'details': [('Part of', str(p.parent or ''), p.parent.get_absolute_url() if p.parent else ''), ('Owner', str(p.owner or ''), ''),
                        ('Department', str(p.department or ''), ''),
                        ('Devices', p.devices.count(), ''), ('Assets and tools', p.assets.count(), ''), ('Orders', p.orders.count(), '')],
            'tables': [_table('Sub-projects', [(_link(c), c.get_status_display()) for c in p.children.order_by('code', 'name')]),
                       _table('Wire diagrams', [(_link(d),) for d in p.wire_diagrams.all()])]}


def vendor(v):
    return {'title': v.name, 'what': v.code, 'edit_url': reverse('inventory:vendor_edit', args=[v.pk]),
            'badges': [] if v.active else [('Inactive', '')],
            'details': [('Email', v.email, f'mailto:{v.email}' if v.email else ''), ('Phone', v.phone, ''), ('Website', v.website, v.website),
                        ('Our account number', v.account_number, ''), ('Address', v.address, '')],
            'tables': [_table('Orders', [((o.number, o.get_absolute_url()), o.get_status_display(), _date(o.ordered_on)) for o in v.orders.all()[:10]]),
                       _table('Parts', [((p.number, p.get_absolute_url()), p.description[:40]) for p in v.parts.filter(active=True)[:15]])]}


def budget(b):
    from budgets import money as sums
    t = sums.totals()[b.pk]
    return {'title': str(b), 'what': '', 'edit_url': reverse('budgets:edit', args=[b.pk]),
            'badges': ([('Overspent', 'failed')] if t.over else []) + ([] if b.active else [('Closed', '')]),
            'details': [('Part of', str(b.parent or ''), b.parent.get_absolute_url() if b.parent else ''),
                        ('Wire diagram', str(b.project or ''), b.project.get_absolute_url() if b.project else ''),
                        ('Department', str(b.department or ''), ''), ('Owner', str(b.owner or ''), ''),
                        ('Amount', money(b.amount), ''), ('Spent', money(t.spent), ''), ('Still to come', money(t.coming), ''),
                        ('Left', money(t.remaining), ''), ('Used', f'{t.used}%', '')],
            'tables': [_table('Budgets in it', [(_link(c), money(c.amount)) for c in b.children.all()]),
                       _table('Orders', [((o.number, o.get_absolute_url()), str(o.vendor or ''), o.get_status_display()) for o in b.orders.select_related('vendor')[:15]])]}


def user(u):
    return {'title': str(u), 'what': u.job_title, 'url': reverse('accounts:user_edit', args=[u.pk]),
            'badges': ([('Administrator', 'ok')] if u.is_superuser else []) + ([] if u.is_active else [("Can't log in", 'failed')]),
            'details': [('User name', u.username, ''), ('Email', u.email, f'mailto:{u.email}' if u.email else ''), ('Phone', u.phone, ''),
                        ('Department', str(u.department or ''), u.department.get_absolute_url() if u.department else ''),
                        ('Last logged in', _date(u.last_login) or 'never', '')],
            'tables': [_table('Has out', [((a.number, a.get_absolute_url()), a.name) for a in u.held_assets.all()[:15]]),
                       _table('Looks after', [((a.number, a.get_absolute_url()), a.name) for a in u.kept_assets.all()[:15]])]}


def location(l):
    from assets.models import Asset
    from inventory.models import Stock
    below, here = l.below(), reverse('inventory:locations')
    return {'title': l.name, 'what': l.description, 'edit_url': reverse('inventory:location_edit', args=[l.pk]),
            'details': [('In', l.parent.path if l.parent else '', f'{here}?location={l.parent_id}' if l.parent else ''),
                        ('Kinds of parts', Stock.objects.filter(location_id__in=below, quantity__gt=0).count(), ''),
                        ('Assets', Asset.objects.filter(location_id__in=below).exclude(status=Asset.Status.RETIRED).count(), '')],
            'tables': [_table('Inside it', [((c.name, f'{here}?location={c.pk}'), c.description[:50]) for c in l.children.all()])]}


BRIEFS = {'location': location, 'device': device, 'order': order, 'diagram': diagram, 'project': project, 'vendor': vendor, 'budget': budget, 'user': user}


def of(kind, obj):
    """What the details pane shows of ``obj`` (a ``kind`` of ``BRIEFS``)."""
    if kind not in BRIEFS:
        raise Http404
    out = {'badges': [], 'tables': [], 'details': [], 'what': '', 'edit_url': '', 'obj': obj, 'kind': kind, **BRIEFS[kind](obj)}
    out.setdefault('url', obj.get_absolute_url() if hasattr(obj, 'get_absolute_url') else '')
    out['details'] = [d for d in out['details'] if d[1] not in ('', None)]
    return out


def find(kind, pk):
    """The thing of ``kind`` numbered ``pk`` (404 when there is none)."""
    from django.shortcuts import get_object_or_404
    if kind == 'user':
        from django.contrib.auth import get_user_model
        return get_object_or_404(get_user_model(), pk=pk)
    from .things import thing
    return thing(kind, pk)
