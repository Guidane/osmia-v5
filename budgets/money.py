"""What a budget has spent: orders charged to it once placed (what has arrived, and what is still to come), its other
costs, and all of that of the budgets under it; drafts are only planned. Telling the owner when it is overspent."""
from decimal import Decimal

from django.db.models import F, Sum

from web.notify import notify

from .models import Budget, Cost

ZERO = Decimal(0)


class Totals:
    def __init__(self, budget, received=ZERO, coming=ZERO, costs=ZERO, planned=ZERO):
        self.budget, self.received, self.coming, self.costs, self.planned = budget, received, coming, costs, planned

    @property
    def spent(self):
        return self.received + self.coming + self.costs

    @property
    def remaining(self):
        return self.budget.amount - self.spent

    @property
    def over(self):
        return self.spent > self.budget.amount

    @property
    def used(self):
        """How much of it is spent, in percent (100 when it has no amount but something is spent)."""
        if self.budget.amount > 0:
            return int(self.spent / self.budget.amount * 100)
        return 100 if self.spent else 0

    def add(self, other):
        self.received += other.received
        self.coming += other.coming
        self.costs += other.costs
        self.planned += other.planned


def _own(budgets):
    """{budget id: Totals} of what is charged to each budget itself."""
    from orders.models import Order, OrderLine
    out = {b.pk: Totals(b) for b in budgets}
    lines = OrderLine.objects.filter(order__budget__in=out, price__isnull=False).values('order__budget', 'order__status').annotate(
        ordered=Sum(F('quantity') * F('price')), arrived=Sum(F('received') * F('price')))
    for row in lines:
        t = out[row['order__budget']]
        status, ordered, arrived = row['order__status'], row['ordered'] or ZERO, row['arrived'] or ZERO
        if status == Order.Status.DRAFT:
            t.planned += ordered
        elif status in Order.OPEN:
            t.received += arrived
            t.coming += ordered - arrived
        elif status == Order.Status.RECEIVED:
            t.received += ordered
        elif status == Order.Status.CANCELLED:
            t.received += arrived   # what came before it was cancelled
    for row in Cost.objects.filter(budget__in=out).values('budget').annotate(n=Sum('amount')):
        out[row['budget']].costs += row['n']
    return out


def totals(budgets=None):
    """{budget id: Totals} for every budget, each with those under it."""
    every = list(Budget.objects.all())
    own = _own(every)
    children = {}
    for b in every:
        children.setdefault(b.parent_id, []).append(b)
    out = {}

    def walk(budget, seen):
        t = Totals(budget, own[budget.pk].received, own[budget.pk].coming, own[budget.pk].costs, own[budget.pk].planned)
        for child in children.get(budget.pk, []):
            if child.pk not in seen:
                t.add(walk(child, seen | {child.pk}))
        out[budget.pk] = t
        return t
    for b in every:
        if b.pk not in out:
            walk(b, {b.pk})
    return out if budgets is None else {b.pk: out[b.pk] for b in budgets}


def own_totals(budget):
    """What is charged to ``budget`` itself (not those under it)."""
    return _own([budget])[budget.pk]


def warn_if_over(budget):
    """Tell the owners of ``budget`` and those above it that are overspent now."""
    every = totals()
    for node in budget.chain():
        t = every[node.pk]
        if t.over and node.owner_id:
            notify([node.owner], f'{node} is overspent: {t.spent:,.2f} of {node.amount:,.2f}.', node.get_absolute_url())
