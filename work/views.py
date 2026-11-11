"""Projects: the list (a tree: sub-projects under the project they are part of), a project's page (its sub-projects;
its wire diagrams, orders, devices, assets and tools, and those of its sub-projects; notes, files and documentation),
making and changing one, and adding things to it or taking them out."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Department
from assets.models import Asset
from devices.models import Device
from orders.models import Order
from projects.models import Project as WireDiagram
from web.forms import TreeForm, initial_for
from web.shortcuts import edit_page

from .models import Project


class ProjectForm(TreeForm):
    tree_fields = {'department': Department}

    class Meta:
        model = Project
        fields = ['code', 'name', 'parent', 'status', 'owner', 'department', 'description', 'notes']
        widgets = {'description': forms.Textarea(attrs={'rows': 3}), 'notes': forms.Textarea(attrs={'rows': 6})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)   # the projects it can be part of: not itself, nor one under it
        inside = self.instance.below() if self.instance.pk else set()
        self.fields['parent'].choices = [('', '—')] + [(p.pk, '\u2003' * depth + str(p)) for p, depth in Project.ordered() if p.pk not in inside]

    def clean_parent(self):
        return self._not_inside_itself('parent', 'A project cannot be part of itself or of one of its sub-projects.')


@login_required
def project_list(request):
    shown = request.GET.get('status', 'active')
    found = Project.objects.select_related('owner').annotate(
        n_diagrams=Count('wire_diagrams', distinct=True), n_orders=Count('orders', distinct=True),
        n_devices=Count('devices', distinct=True), n_assets=Count('assets', distinct=True))
    if shown in Project.Status.values:
        found = found.filter(status=shown)
    q = request.GET.get('q', '').strip()
    if q:
        found = found.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
    every = {p.pk: p for p in Project.objects.select_related('owner').annotate(
        n_diagrams=Count('wire_diagrams', distinct=True), n_orders=Count('orders', distinct=True),
        n_devices=Count('devices', distinct=True), n_assets=Count('assets', distinct=True))}
    matched = set(found.values_list('pk', flat=True))
    shown_pks = set(matched)   # those found, and the projects they are part of (to stand under)
    for pk in matched:
        shown_pks.update(every[pk].chain_pks())
    rows = []
    for p, depth in Project.ordered(every.values()):
        if p.pk in shown_pks:
            p.depth, p.matched = depth, p.pk in matched
            rows.append(p)
    return render(request, 'work/list.html', {'projects': rows, 'shown': shown, 'statuses': Project.Status.choices, 'q': q})


@login_required
def project_form(request, pk=None):
    item = get_object_or_404(Project, pk=pk) if pk else None
    initial = initial_for(item, owner=request.user.pk, parent=request.GET.get('parent'))
    return edit_page(request, ProjectForm(request.POST or None, instance=item, initial=initial), 'project')


@login_required
def project(request, pk):
    item = get_object_or_404(Project.objects.select_related('owner', 'department'), pk=pk)
    assets = list(item.assets.select_related('location', 'keeper'))
    under = {p.pk: p for p in Project.objects.filter(pk__in=item.below() - {item.pk})}   # its sub-projects, all the way down

    def rolled(things, own, via):   # what its sub-projects have (and it hasn't itself), each with the sub-project it is from
        seen, out = {t.pk for t in own}, []
        for t in things:
            if t.pk not in seen:
                seen.add(t.pk)
                t.via = under[via(t)]
                out.append(t)
        return out
    sub_assets = rolled(Asset.objects.filter(work_projects__in=under).select_related('location').annotate(via_pk=Min('work_projects', filter=Q(work_projects__in=under))).order_by('number'),
                        assets, lambda t: t.via_pk)
    context = {
        'project': item,
        'children': item.children.order_by('code', 'name'),
        'sub_diagrams': rolled(WireDiagram.objects.filter(in_project__in=under).prefetch_related('harnesses'), [], lambda t: t.in_project_id),
        'sub_orders': rolled(Order.objects.filter(in_project__in=under).select_related('vendor'), [], lambda t: t.in_project_id),
        'sub_devices': rolled(Device.objects.filter(work_projects__in=under).annotate(via_pk=Min('work_projects', filter=Q(work_projects__in=under))).order_by('number'),
                              item.devices.all(), lambda t: t.via_pk),
        'sub_assets': [a for a in sub_assets if a.kind != Asset.Kind.TOOL],
        'sub_tools': [a for a in sub_assets if a.kind == Asset.Kind.TOOL],
        'diagrams': item.wire_diagrams.prefetch_related('harnesses'),
        'orders': item.orders.select_related('vendor', 'created_by'),
        'devices': item.devices.all(),
        'assets': [a for a in assets if a.kind != Asset.Kind.TOOL],
        'tools': [a for a in assets if a.kind == Asset.Kind.TOOL],
        'free_diagrams': WireDiagram.objects.filter(in_project=None),
        'free_orders': Order.objects.filter(in_project=None).exclude(status=Order.Status.CANCELLED).order_by('-number')[:200],
        'other_devices': Device.objects.exclude(pk__in=item.devices.values('pk')),
        'other_assets': Asset.objects.exclude(pk__in=item.assets.values('pk')).exclude(kind=Asset.Kind.TOOL),
        'other_tools': Asset.objects.exclude(pk__in=item.assets.values('pk')).filter(kind=Asset.Kind.TOOL),
    }
    context['n_sub'] = {k: len(context['sub_' + k]) for k in ('diagrams', 'orders', 'devices', 'assets', 'tools')}
    return render(request, 'work/project.html', context)


@login_required
@require_POST
def link(request, pk):
    """Something put into the project, or taken out (``remove``): a wire diagram, an order, a device, an asset."""
    item = get_object_or_404(Project, pk=pk)
    what, thing_id, out = request.POST.get('what'), request.POST.get('id') or 0, bool(request.POST.get('remove'))
    if what in ('diagram', 'order'):
        thing = get_object_or_404(WireDiagram if what == 'diagram' else Order, pk=thing_id)
        if out and thing.in_project_id == item.pk:
            thing.in_project = None
        elif not out:
            thing.in_project = item
        thing.save(update_fields=['in_project'])
    elif what in ('device', 'asset'):
        thing = get_object_or_404(Device if what == 'device' else Asset, pk=thing_id)
        (item.devices if what == 'device' else item.assets).remove(thing) if out else \
            (item.devices if what == 'device' else item.assets).add(thing)
    else:
        return redirect(item)
    messages.success(request, f'{thing} is {"taken out of" if out else "in"} {item}.')
    return redirect(item)
