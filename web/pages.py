"""Documentation pages, like a wiki: each has a title and its text (written in the editor; cleaned, see ``web.markup``),
may sit under another page, and belongs to something (a project, a part, a device, …) or to the general documentation.
Every save is kept: a page's history shows each version, and an old one can be brought back."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .files import delete_files_of
from .markup import clean
from .models import Page, PageVersion
from .things import KINDS, files_of, kind_of, owner_of, pages_of, thing, tree


def _plural(name):
    return name[:-1] + 'ies' if name.endswith('y') else name + 'es' if name.endswith('s') else name + 's'


def _space(page):
    """The pages of the same place as ``page`` (the same thing, or the general documentation)."""
    if page.content_type_id is None:
        return Page.objects.filter(content_type=None)
    return Page.objects.filter(content_type_id=page.content_type_id, object_id=page.object_id)


def _crumbs(owner):
    """Documentation › the thing the page belongs to."""
    crumbs = [(reverse('web:docs'), 'Documentation')]
    if owner is not None:
        crumbs.append((owner.get_absolute_url(), f'{KINDS[kind_of(owner)][1]} {owner}'))
    return crumbs


@login_required
def docs(request):
    """The documentation: its general pages as a tree, the projects and other things with pages, the pages changed
    last; and finding pages by what they say."""
    q = request.GET.get('q', '').strip()
    found = Page.objects.filter(Q(title__icontains=q) | Q(body__icontains=q)).select_related('updated_by')[:50] if q else None
    owners = {}
    for ct, obj in Page.objects.exclude(content_type=None).order_by().values_list('content_type', 'object_id').distinct():
        owner = owner_of(ct, obj)
        if owner is not None:
            owners.setdefault(kind_of(owner), []).append(owner)
    groups = [(_plural(name), [(o, pages_of(o)) for o in sorted(owners[kind], key=str)]) for kind, (_, name) in KINDS.items()
              if kind in owners]
    return render(request, 'web/docs.html', {'general': pages_of(None), 'groups': groups, 'q': q, 'found': found,
                                             'recent': Page.objects.select_related('updated_by').order_by('-updated_at')[:10]})


@login_required
def page(request, pk):
    item = get_object_or_404(Page.objects.select_related('updated_by', 'created_by'), pk=pk)
    owner = item.owner
    return render(request, 'web/page.html', {
        'page': item, 'owner': owner, 'crumbs': _crumbs(owner), 'ancestors': item.ancestors(),
        'children': item.children.all(), 'tree': tree(_space(item)), 'files': files_of(item),
        'version': item.versions.aggregate(n=Max('number'))['n'] or 0})


class PageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = ['title', 'parent']

    def __init__(self, *args, space=None, **kwargs):
        super().__init__(*args, **kwargs)
        mine = {self.instance.pk, *(p.pk for p in self.instance.below())} if self.instance.pk else set()
        self.fields['parent'].choices = [('', '—')] + [(p.pk, '   ' * depth + p.title) for p, depth in tree(space)
                                                        if p.pk not in mine]
        self.fields['parent'].queryset = space.exclude(pk__in=mine)
        self.fields['title'].widget.attrs.update({'autofocus': True, 'class': 'page-title-input'})


def _save(request, item, form, new):
    """The page saved from the editor, and kept as a new version when it changed."""
    with transaction.atomic():
        item = form.save(commit=False)
        body = clean(request.POST.get('body', ''))
        last = item.versions.first() if item.pk else None
        item.body, item.updated_by = body, request.user
        if new:
            item.created_by = request.user
        item.save()
        if last is None or last.title != item.title or last.body != item.body:
            PageVersion.objects.create(page=item, number=(last.number if last else 0) + 1, title=item.title, body=body,
                                       saved_by=request.user)
    return item


@login_required
def page_new(request):
    """A new page: under ``?parent=`` (in its place), or of ``?kind=&pk=`` (a project, a part, …), or general."""
    parent = Page.objects.filter(pk=request.GET.get('parent') or 0).first()
    owner = parent.owner if parent else (thing(request.GET['kind'], request.GET.get('pk') or 0) if request.GET.get('kind') else None)
    item = Page(parent=parent)
    if parent is not None:
        item.content_type_id, item.object_id = parent.content_type_id, parent.object_id
    elif owner is not None:
        item.content_type, item.object_id = ContentType.objects.get_for_model(owner), owner.pk
    form = PageForm(request.POST or None, instance=item, initial={'parent': parent.pk if parent else None}, space=_space(item))
    if request.method == 'POST' and form.is_valid():
        item = _save(request, item, form, new=True)
        messages.success(request, f'{item} is saved.')
        return redirect(item)
    return render(request, 'web/page_form.html', {'form': form, 'page': item, 'owner': owner, 'crumbs': _crumbs(owner),
                                                  'body': request.POST.get('body', '')})


@login_required
def page_edit(request, pk):
    item = get_object_or_404(Page, pk=pk)
    form = PageForm(request.POST or None, instance=item, space=_space(item))
    if request.method == 'POST' and form.is_valid():
        item = _save(request, item, form, new=False)
        messages.success(request, f'{item} is saved.')
        return redirect(item)
    return render(request, 'web/page_form.html', {'form': form, 'page': item, 'owner': item.owner, 'crumbs': _crumbs(item.owner),
                                                  'body': request.POST.get('body', item.body)})


@login_required
@require_POST
def page_delete(request, pk):
    """The page and the pages under it, with their files."""
    item = get_object_or_404(Page, pk=pk)
    back = item.parent.get_absolute_url() if item.parent else (item.owner.get_absolute_url() if item.owner else reverse('web:docs'))
    with transaction.atomic():
        for p in [item] + item.below():
            delete_files_of(p)
        item.delete()
    messages.success(request, f'{item} is deleted.')
    return redirect(back)


@login_required
def history(request, pk):
    """Every saved version of the page (``?v=``: one of them, as it was)."""
    item = get_object_or_404(Page, pk=pk)
    versions = item.versions.select_related('saved_by')
    shown = versions.filter(number=request.GET.get('v') or 0).first()
    return render(request, 'web/page_history.html', {'page': item, 'versions': versions, 'shown': shown,
                                                     'crumbs': _crumbs(item.owner)})


@login_required
@require_POST
def restore(request, pk, number):
    item = get_object_or_404(Page, pk=pk)
    old = get_object_or_404(PageVersion, page=item, number=number)
    with transaction.atomic():
        item.title, item.body, item.updated_by = old.title, old.body, request.user
        item.save()
        last = item.versions.first()
        PageVersion.objects.create(page=item, number=last.number + 1, title=old.title, body=old.body, saved_by=request.user)
    messages.success(request, f'{item} is as it was in version {number}.')
    return redirect(item)
