"""The website's own pages: the first run, Home and notifications."""
from django.contrib import messages
from django.contrib.auth import get_user_model, login, password_validation
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Notification


def setup(request):
    """The first run: make the administrator account."""
    User = get_user_model()
    if User.objects.filter(is_superuser=True).exists():
        return redirect('web:home')
    errors, values = [], {}
    if request.method == 'POST':
        values = request.POST
        username = values.get('username', '').strip()
        p1, p2 = values.get('password1', ''), values.get('password2', '')
        if not username:
            errors.append('Choose a user name.')
        if p1 != p2:
            errors.append('The two passwords are not the same.')
        candidate = User(username=username, email=values.get('email', '').strip(),
                         first_name=values.get('first_name', '').strip(), last_name=values.get('last_name', '').strip())
        if not errors:
            try:
                password_validation.validate_password(p1, candidate)
            except ValidationError as exc:
                errors.extend(exc.messages)
        if not errors:
            candidate.is_superuser = candidate.is_staff = True
            candidate.set_password(p1)
            candidate.save()
            from . import middleware
            middleware._ready = True
            login(request, candidate, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Osmia is ready.')
            return redirect('web:home')
    return render(request, 'web/setup.html', {'errors': errors, 'values': values})


REPORTS = [   # what Home can show: (key, title, on Home as it comes)
    ('glance', 'At a glance', True), ('harness_requests', 'Harnesses asked for', True), ('waiting', 'Still to come', True),
    ('to_order', 'Below their minimum', True), ('assets_due', 'Due for calibration', True), ('received', 'Arrived lately', True),
    ('my_assets', 'What I have out', False), ('projects', 'Active projects', False), ('drafts', 'Drafts and requests', False),
    ('building', 'Being built', False), ('budgets', 'Budgets overspent', False),
]


def home_reports_of(user):
    """The reports on ``user``'s Home, in their order: their own pick, else those it comes with."""
    known = {key for key, _, _ in REPORTS}
    if user.home_reports is None:
        return [key for key, _, shown in REPORTS if shown]
    return [key for key in user.home_reports if key in known]


@login_required
def home(request):
    """What needs attention, in reports each person picks for themselves (Edit: a ✕ on each, ＋ Add report): parts to
    order, orders still to come (late ones first), budgets overspent, what arrived lately, …"""
    from projects.models import HarnessRequest
    from datetime import date

    from assets.models import Asset
    from orders.models import Order
    from orders.service import needs_ordering
    from work.models import Project
    waiting = sorted(Order.objects.filter(status__in=Order.OPEN).select_related('vendor'),
                     key=lambda o: (not o.overdue, o.expected_on or date.max))
    from budgets.money import totals
    from assets.service import due
    over = [t.budget for t in totals().values() if t.over and t.budget.active]
    mine = home_reports_of(request.user)
    titles = {key: title for key, title, _ in REPORTS}
    return render(request, 'web/home.html', {
        'reports': [(key, titles[key], f'web/home/{key}.html') for key in mine],
        'addable': [(key, title) for key, title, _ in REPORTS if key not in mine],
        'editing': bool(request.GET.get('edit')),
        'assets_due': due(),
        'over_budget': over,
        'to_order': needs_ordering(), 'waiting': waiting, 'late': sum(1 for o in waiting if o.overdue),
        'drafts': Order.objects.filter(status=Order.Status.DRAFT, kind=Order.Kind.ORDER).count(),
        'requests': Order.objects.filter(status=Order.Status.DRAFT, kind=Order.Kind.REQUEST).count(),
        'harness_requests': HarnessRequest.objects.filter(status='open').select_related('configuration__project', 'created_by', 'ask'),
        'received': Order.objects.filter(status=Order.Status.RECEIVED).select_related('vendor').order_by('-received_on', '-pk')[:8],
        'my_assets': Asset.objects.filter(holder=request.user).select_related('location') if 'my_assets' in mine else [],
        'active_projects': Project.objects.filter(status=Project.Status.ACTIVE, parent=None).select_related('owner') if 'projects' in mine else [],
        'draft_orders': Order.objects.filter(status=Order.Status.DRAFT).select_related('vendor', 'created_by')[:20] if 'drafts' in mine else [],
        'building': Asset.objects.filter(status=Asset.Status.BUILDING).select_related('built_by') if 'building' in mine else []})


@login_required
@require_POST
def home_reports(request):
    """A report put on one's Home (at the end), taken off it, or Home put back as it comes."""
    user, action, key = request.user, request.POST.get('action'), request.POST.get('key', '')
    mine = home_reports_of(user)
    if action == 'reset':
        user.home_reports = None
    elif key in {k for k, _, _ in REPORTS}:
        user.home_reports = [k for k in mine if k != key] + ([key] if action == 'add' else [])
    user.save(update_fields=['home_reports'])
    return redirect(reverse('web:home') + '?edit=1')


@login_required
def demo_data(request):
    """Administrators switch the demo data on and off."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from . import demo
    from .models import DemoRecord
    if not request.user.is_superuser:
        raise Http404
    if request.method == 'POST':
        try:
            if request.POST.get('action') == 'on':
                demo.switch_on(request.user)
                messages.success(request, 'The demo data is on.')
            else:
                kept = demo.switch_off()
                messages.success(request, 'The demo data is off: everything it made is gone.')
                if kept:
                    messages.warning(request, f'Kept, because real data uses them now: {", ".join(kept)}.')
        except ValidationError as exc:
            for message in exc.messages:
                messages.error(request, message)
        return redirect('web:demo')
    return render(request, 'web/demo.html', {'on': demo.is_on(), 'rows': DemoRecord.objects.count()})


@login_required
def transfer(request):
    """Administrators export all the data to a file, or replace it all with an export (from another Osmia)."""
    from datetime import datetime

    from django.contrib.auth import logout
    from django.core.exceptions import ValidationError
    from django.http import FileResponse, Http404

    from . import backup
    if not request.user.is_superuser:
        raise Http404
    if request.method == 'POST' and request.POST.get('action') == 'export':
        import tempfile
        out = tempfile.TemporaryFile()
        backup.export_to(out)
        out.seek(0)
        return FileResponse(out, as_attachment=True, filename=f'osmia-{datetime.now():%Y-%m-%d-%H%M}.zip')
    if request.method == 'POST':
        upload = request.FILES.get('file')
        if upload is None or not request.POST.get('sure'):
            messages.error(request, 'Pick the export, and tick that all the data here is to be replaced.')
            return redirect('web:transfer')
        try:
            manifest = backup.import_from(upload)
        except ValidationError as exc:
            for message in exc.messages:
                messages.error(request, message)
            return redirect('web:transfer')
        logout(request)   # who is logged in, and how, is the export's now
        messages.success(request, f'The data exported on {manifest["made"]} is in. Log in with an account of that data.')
        return redirect('accounts:login')
    return render(request, 'web/transfer.html')


@login_required
def update_osmia(request):
    """Administrators install a newer Osmia from its code (.zip): see web.update."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from osmia.version import VERSION

    from . import update
    if not request.user.is_superuser:
        raise Http404
    if request.method == 'POST':
        upload = request.FILES.get('file')
        if upload is None:
            messages.error(request, "Pick the .zip with Osmia's code.")
            return redirect('web:update')
        try:
            release, again = update.update(upload)
        except ValidationError as exc:
            for message in exc.messages:
                messages.error(request, message)
            return redirect('web:update')
        return render(request, 'web/updated.html', {'release': release, 'again': again, 'was': VERSION})
    return render(request, 'web/update.html', {'version': VERSION})


@login_required
def notifications(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, read=False).update(read=True)
        return redirect('web:notifications')
    return render(request, 'web/notifications.html', {'items': Notification.objects.filter(user=request.user)[:200]})


@login_required
def notification_open(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    note.read = True
    note.save(update_fields=['read'])
    return redirect(note.url or 'web:notifications')


@login_required
@require_POST
def notes(request, kind, pk):
    """The notes of a thing (``web.things``) changed in place, from its Notes card."""
    from .things import thing
    obj = thing(kind, pk)
    if not hasattr(obj, 'notes'):
        raise Http404
    obj.notes = request.POST.get('notes', '').strip()
    obj.save(update_fields=['notes'])
    back = request.POST.get('next', '')
    return redirect(back if back.startswith('/') and not back.startswith('//') else obj.get_absolute_url())


@login_required
def brief(request, kind, pk):
    """The details of a thing beside its list (fetched when a row is picked): see ``web.briefs``."""
    from . import briefs
    return render(request, 'web/_brief.html', {'brief': briefs.of(kind, briefs.find(kind, pk))})
