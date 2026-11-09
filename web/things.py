"""The things files and documentation pages can belong to, each named in addresses by its kind (/files/part/12/), and
what each has: its files, its preview picture, its pages."""
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import get_object_or_404

KINDS = {   # kind: (model, what one is called)
    'project': ('work.Project', 'Project'), 'diagram': ('projects.Project', 'Wire diagram'), 'harness': ('harnesses.Harness', 'Harness'),
    'device': ('devices.Device', 'Device'), 'part': ('inventory.Part', 'Part'), 'family': ('inventory.Family', 'Family'),
    'order': ('orders.Order', 'Order'), 'vendor': ('inventory.Vendor', 'Vendor'), 'budget': ('budgets.Budget', 'Budget'),
    'asset': ('assets.Asset', 'Asset'), 'location': ('inventory.Location', 'Location'), 'page': ('web.Page', 'Page'),
}


def kind_of(obj):
    label = obj._meta.label_lower
    return next(k for k, (model, _) in KINDS.items() if model.lower() == label)


def thing(kind, pk):
    if kind not in KINDS:
        raise Http404
    return get_object_or_404(apps.get_model(KINDS[kind][0]), pk=pk)


def owner_of(content_type_id, object_id):
    """The thing a content type and id point to (None if it is gone)."""
    model = ContentType.objects.get_for_id(content_type_id).model_class()
    return model.objects.filter(pk=object_id).first() if model else None


def files_of(obj):
    from .models import Attachment
    return Attachment.objects.filter(content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk)


def preview_of(obj):
    return files_of(obj).filter(preview=True).first()


def pages_of(obj):
    """The pages that belong to ``obj`` (None: the general documentation), as a tree: [(page, depth)]."""
    from .models import Page
    if obj is None:
        found = Page.objects.filter(content_type=None)
    else:
        found = Page.objects.filter(content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk)
    return tree(found)


def tree(pages):
    children = {}
    for p in pages.order_by('position', 'title'):
        children.setdefault(p.parent_id, []).append(p)
    out = []

    def walk(parent, depth):
        for p in children.get(parent, []):
            out.append((p, depth))
            walk(p.pk, depth + 1)
    walk(None, 0)
    return out
