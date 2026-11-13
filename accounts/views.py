"""People's own profile; and, for administrators, the users (making them, changing them, which department they are
in) and the departments (everyone can see them and who is in them)."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from web import excel
from web.shortcuts import edit_page
from web.forms import initial_for

from .forms import DepartmentForm, ProfileForm, UserForm
from .models import Department, User


def administrators(view):
    @wraps(view)
    @login_required
    def only(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return view(request, *args, **kwargs)
    return only


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your profile is saved.')
        return redirect('accounts:profile')
    return render(request, 'accounts/profile.html', {'form': form})


@administrators
def users(request):
    q = request.GET.get('q', '').strip()
    found = User.objects.select_related('department')
    if q:
        found = found.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
                             | Q(email__icontains=q) | Q(job_title__icontains=q))
    department = Department.objects.filter(pk=request.GET.get('department') or 0).first()
    if department is not None:
        found = found.filter(department_id__in=department.below())
    if request.GET.get('none'):
        found = found.filter(department=None)
    if not request.GET.get('all'):
        found = found.filter(is_active=True)
    if request.GET.get('export'):
        return excel.download('users', [('Users', ['User name', 'Name', 'Email', 'Job title', 'Phone', 'Department', 'Administrator',
                                                   'Can log in', 'Last logged in'],
                                         [(u.username, u.get_full_name(), u.email, u.job_title, u.phone, u.department.path if u.department else '',
                                           'yes' if u.is_superuser else '', 'yes' if u.is_active else 'no', u.last_login) for u in found])])
    from web import briefs, browse
    everyone = User.objects.all() if request.GET.get('all') else User.objects.filter(is_active=True)
    own = dict(everyone.exclude(department=None).values('department').annotate(n=Count('pk')).values_list('department', 'n'))
    kept = browse.keep(request, 'q', 'all')
    loose = bool(request.GET.get('none'))
    nodes = [browse.node('Everyone', f'?{kept[1:]}', everyone.count(), department is None and not loose)] + browse.nodes(
        Department.ordered(), own, department, lambda d: f'?department={d.pk}{kept}', label=lambda d: d.name) + [
        browse.node('In no department', f'?none=1{kept}', everyone.filter(department=None).count(), loose)]
    picked = User.objects.filter(pk=request.GET.get('user') or 0).first()
    return render(request, 'accounts/users.html', {'users': found, 'q': q, 'department': department, 'nodes': nodes, 'loose': loose,
                                                   'picked': picked, 'brief': briefs.of('user', picked) if picked else None})


@administrators
def user_form(request, pk=None):
    person = get_object_or_404(User, pk=pk) if pk else None
    return edit_page(request, UserForm(request.POST or None, instance=person, by=request.user,
                                       initial=initial_for(person, department=request.GET.get('department'), is_active=True)),
                     'user', then='accounts:users')


@login_required
def departments(request):
    members = dict(User.objects.filter(is_active=True).values('department').annotate(n=Count('pk')).values_list('department', 'n'))
    return render(request, 'accounts/departments.html', {
        'departments': [(d, depth, members.get(d.pk, 0)) for d, depth in Department.ordered()],
        'without': User.objects.filter(is_active=True, department=None).count()})


@login_required
def department(request, pk):
    item = get_object_or_404(Department.objects.select_related('parent', 'manager'), pk=pk)
    people = item.members.filter(is_active=True)
    return render(request, 'accounts/department.html', {
        'department': item, 'people': people, 'children': item.children.all(),
        'budgets': item.budgets.all(), 'projects': item.projects.all(),
        'others': User.objects.filter(is_active=True).exclude(department=item).select_related('department')})


@administrators
def department_form(request, pk=None):
    item = get_object_or_404(Department, pk=pk) if pk else None
    return edit_page(request, DepartmentForm(request.POST or None, instance=item, initial=initial_for(item, parent=request.GET.get('parent'))),
                     'department')


@administrators
@require_POST
def assign(request, pk):
    """Put people in this department (out of the one they were in), or take one out of it."""
    item = get_object_or_404(Department, pk=pk)
    if request.POST.get('remove'):
        User.objects.filter(pk=request.POST['remove'], department=item).update(department=None)
    else:
        chosen = User.objects.filter(pk__in=request.POST.getlist('users'))
        names = ', '.join(str(u) for u in chosen)
        chosen.update(department=item)
        if names:
            messages.success(request, f'In {item.name} now: {names}.')
    return redirect(item)


@administrators
@require_POST
def department_delete(request, pk):
    item = get_object_or_404(Department, pk=pk)
    if item.children.exists():
        messages.error(request, f'{item.name} has departments under it: move or delete those first.')
        return redirect(item)
    item.members.update(department=None)
    item.delete()
    messages.success(request, f'{item.name} is deleted; its people are in no department now.')
    return redirect('accounts:departments')
