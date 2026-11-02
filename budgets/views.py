"""Budgets: the tree with what each has spent and has left, a budget's page (its orders, other costs and the budgets
under it) and changing them."""
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Department
from inventory.stock import amount
from web import excel
from web.shortcuts import edit_page
from web.forms import TreeForm, initial_for

from . import money
from .models import Budget, Cost


class BudgetForm(TreeForm):
    tree_fields = {'parent': Budget, 'department': Department}

    class Meta:
        model = Budget
        fields = ['number', 'name', 'parent', 'department', 'project', 'owner', 'amount', 'starts_on', 'ends_on', 'notes', 'active']
        labels = {'parent': 'Part of'}
        widgets = {'starts_on': forms.DateInput(attrs={'type': 'date'}), 'ends_on': forms.DateInput(attrs={'type': 'date'}),
                   'notes': forms.Textarea(attrs={'rows': 3})}

    def clean_parent(self):
        return self._not_inside_itself('parent', "A budget can't be part of itself.")


def _rows(totals):
    """Each budget, depth first, with its totals: [(budget, depth, totals)]."""
    return [(b, depth, totals[b.pk]) for b, depth in Budget.ordered()]


@login_required
def budget_list(request):
    totals = money.totals()
    rows = _rows(totals)
    if not request.GET.get('all'):
        rows = [r for r in rows if r[0].active]
    if request.GET.get('export'):
        return excel.download('budgets', [('Budgets', ['Number', 'Name', 'Part of', 'Project', 'Owner', 'Amount', 'Received',
                                                       'Still to come', 'Other costs', 'Spent', 'Left', 'Used %', 'In drafts'],
                                           [(b.number, b.name, str(b.parent or ''), str(b.project or ''), str(b.owner or ''), b.amount,
                                             t.received, t.coming, t.costs, t.spent, t.remaining, t.used, t.planned) for b, _, t in rows])])
    return render(request, 'budgets/list.html', {'rows': rows})


@login_required
def budget_form(request, pk=None):
    item = get_object_or_404(Budget, pk=pk) if pk else None
    return edit_page(request, BudgetForm(request.POST or None, instance=item, initial=initial_for(
        item, parent=request.GET.get('parent'), project=request.GET.get('project'), owner=request.user.pk)), 'budget')


@login_required
def budget(request, pk):
    item = get_object_or_404(Budget.objects.select_related('parent', 'project', 'owner'), pk=pk)
    totals = money.totals()
    orders = list(item.orders.select_related('vendor').prefetch_related('lines'))
    costs = item.costs.select_related('created_by')
    if request.GET.get('export'):
        return excel.download(str(item), [
            ('Orders', ['Order', 'Vendor', 'Status', 'Ordered', 'Value'], [(o.number, o.vendor.name, o.get_status_display(), o.ordered_on, o.total) for o in orders]),
            ('Other costs', ['Date', 'Description', 'Amount', 'By'], [(c.spent_on, c.description, c.amount, str(c.created_by or '')) for c in costs]),
            ('Under it', ['Number', 'Name', 'Amount', 'Spent', 'Left'],
             [(c.number, c.name, c.amount, totals[c.pk].spent, totals[c.pk].remaining) for c in item.children.all()])])
    below = item.children.all()
    return render(request, 'budgets/budget.html', {
        'budget': item, 'totals': totals[item.pk], 'own': money.own_totals(item), 'orders': orders, 'costs': costs,
        'children': [(c, totals[c.pk]) for c in below], 'split': sum(c.amount for c in below), 'today': date.today()})


@login_required
@require_POST
def cost_add(request, pk):
    item = get_object_or_404(Budget, pk=pk)
    try:
        value = amount(request.POST.get('amount'))
        description = request.POST.get('description', '').strip()
        if not description:
            raise forms.ValidationError('Say what it was for.')
        spent_on = date.fromisoformat(request.POST.get('spent_on') or date.today().isoformat())
    except (forms.ValidationError, ValueError) as exc:
        for message in getattr(exc, 'messages', ['That is not a date.']):
            messages.error(request, message)
        return redirect(item)
    Cost.objects.create(budget=item, amount=value, description=description[:300], spent_on=spent_on, created_by=request.user)
    money.warn_if_over(item)
    return redirect(f'{item.get_absolute_url()}#costs')


@login_required
@require_POST
def cost_delete(request, pk, cost):
    get_object_or_404(Cost, pk=cost, budget_id=pk).delete()
    return redirect(f'{Budget.objects.get(pk=pk).get_absolute_url()}#costs')
