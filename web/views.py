"""The website's own pages: the first run, Home and notifications."""
from django.contrib import messages
from django.contrib.auth import get_user_model, login, password_validation
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

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


@login_required
def home(request):
    """What needs attention: parts to order, orders still to come (late ones first), budgets overspent, what arrived
    lately."""
    from datetime import date

    from orders.models import Order
    from orders.service import needs_ordering
    waiting = sorted(Order.objects.filter(status__in=Order.OPEN).select_related('vendor'),
                     key=lambda o: (not o.overdue, o.expected_on or date.max))
    from budgets.money import totals
    from assets.service import due
    over = [t.budget for t in totals().values() if t.over and t.budget.active]
    return render(request, 'web/home.html', {
        'assets_due': due(),
        'over_budget': over,
        'to_order': needs_ordering(), 'waiting': waiting, 'late': sum(1 for o in waiting if o.overdue),
        'drafts': Order.objects.filter(status=Order.Status.DRAFT).select_related('vendor'),
        'received': Order.objects.filter(status=Order.Status.RECEIVED).select_related('vendor').order_by('-received_on', '-pk')[:8]})


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
