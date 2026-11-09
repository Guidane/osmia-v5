"""Projects: the list, a project's page (its wire diagrams, orders, devices, assets and tools, notes, files and
documentation), making and changing one, and adding things to it or taking them out."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
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
        fields = ['code', 'name', 'status', 'owner', 'department', 'description', 'notes']
        widgets = {'description': forms.Textarea(attrs={'rows': 3}), 'notes': forms.Textarea(attrs={'rows': 6})}


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
    return render(request, 'work/list.html', {'projects': found, 'shown': shown, 'statuses': Project.Status.choices, 'q': q})


@login_required
def project_form(request, pk=None):
    item = get_object_or_404(Project, pk=pk) if pk else None
    return edit_page(request, ProjectForm(request.POST or None, instance=item, initial=initial_for(item, owner=request.user.pk)), 'project')


@login_required
def project(request, pk):
    item = get_object_or_404(Project.objects.select_related('owner', 'department'), pk=pk)
    assets = list(item.assets.select_related('location', 'keeper'))
    return render(request, 'work/project.html', {
        'project': item,
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
    })


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
