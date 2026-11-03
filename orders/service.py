"""What happens to orders: reordering a part, placing an order, receiving what arrived (into stock), cancelling."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum

from inventory import stock
from inventory.models import Movement, Part
from web.notify import notify

from .models import Order, OrderLine


def _draft_for(vendor, user):
    order = Order.objects.filter(vendor=vendor, kind=Order.Kind.ORDER, status=Order.Status.DRAFT).order_by('-pk').first()
    return order or Order.objects.create(vendor=vendor, created_by=user)


@transaction.atomic
def order_asset(asset, user):
    """Put ``asset`` (one on order) on the draft order for its vendor (a new one if there is none). Returns the line."""
    from assets.models import Asset
    if asset.status != Asset.Status.ORDERED:
        raise ValidationError(f'{asset} is not on order: an asset to buy is made "On order" first.')
    if asset.vendor_id is None:
        raise ValidationError(f'{asset} has no vendor: say where it is bought first.')
    if OrderLine.objects.filter(asset=asset).exclude(order__status=Order.Status.CANCELLED).exists():
        raise ValidationError(f'{asset} is on an order already.')
    return OrderLine.objects.create(order=_draft_for(asset.vendor, user), asset=asset, quantity=1, price=asset.price)


def on_order(part):
    """How many of ``part`` (or of the parts of a family) are ordered and not yet received."""
    lines = OrderLine.objects.filter(order__status__in=Order.OPEN)
    lines = lines.filter(part__family=part) if hasattr(part, 'chosen') else lines.filter(part=part)
    left = lines.aggregate(n=Sum(F('quantity') - F('received')))['n']
    return max(left or Decimal(0), Decimal(0))


def needs_ordering():
    """The active parts whose stock, with what is on order, is below their minimum: [(part, on hand, on order)]."""
    out = []
    for part in Part.objects.filter(active=True, minimum__gt=0).select_related('vendor'):
        have, coming = part.on_hand, on_order(part)
        if have + coming < part.minimum:
            out.append((part, have, coming))
    return out


@transaction.atomic
def reorder(part, user, quantity=None):
    """Put ``part`` on the draft order for its vendor (a new one if there is none): ``quantity``, else its reorder
    quantity, else enough to get back above its minimum. Returns the line."""
    if part.vendor_id is None:
        raise ValidationError(f'{part} has no vendor: say where it is ordered first.')
    order = _draft_for(part.vendor, user)
    wanted = quantity or part.reorder_quantity or max(part.minimum - part.on_hand - on_order(part), Decimal(1))
    line = order.lines.filter(part=part).first()
    if line is None:
        line = OrderLine.objects.create(order=order, part=part, quantity=wanted, price=part.price)
    else:
        line.quantity += wanted
        line.save(update_fields=['quantity'])
    return line


def ask(order):
    """A request is made: who should order it (else the administrators) hears of it."""
    from django.contrib.auth import get_user_model
    people = [order.ask] if order.ask else list(get_user_model().objects.filter(is_superuser=True, is_active=True))
    people = [p for p in people if p != order.created_by] or people
    notify(people, f'{order.created_by or "Someone"} asks to order: {order.request[:200]}', order.get_absolute_url())


@transaction.atomic
def place(order, user, expected_on=None):
    """The order went to the vendor: from now on it is waiting for its parts. Who asked for it hears."""
    if order.status != Order.Status.DRAFT:
        raise ValidationError(f'{order} is {order.get_status_display().lower()} already.')
    if not order.lines.exists():
        raise ValidationError(f'{order} has nothing on it yet.')
    if order.vendor_id is None:
        raise ValidationError(f'Say who {order} is ordered from first.')
    order.status, order.ordered_on = Order.Status.ORDERED, date.today()
    order.expected_on = expected_on or order.expected_on
    order.save()
    for line in order.lines.filter(part__isnull=False).select_related('part'):   # the price ordered at is the part's last price
        if line.price is not None and line.part.price != line.price:
            Part.objects.filter(pk=line.part_id).update(price=line.price)
    if order.budget_id:
        from budgets.money import warn_if_over
        warn_if_over(order.budget)
    if order.kind == Order.Kind.REQUEST and order.created_by and order.created_by != user:
        notify([order.created_by], f'What you asked for is ordered from {order.vendor}: {order}.', order.get_absolute_url())


@transaction.atomic
def receive(order, arrived, user):
    """What arrived for ``order``: [(line, quantity, location)], booked into stock. The order is received when
    nothing is outstanding; whoever made it hears what came."""
    if order.status not in Order.OPEN:
        raise ValidationError(f'{order} is {order.get_status_display().lower()}: there is nothing to receive.')
    booked = []
    for line, quantity, location in arrived:
        if line.order_id != order.pk:
            raise ValidationError('That line is on another order.')
        quantity = stock.amount(quantity)
        if location is None:
            raise ValidationError(f'Say where the {line.item} goes.')
        if quantity > line.outstanding:
            raise ValidationError(f'Only {line.outstanding.normalize():f} of {line.item} are still to come.')
        if line.asset_id:
            _asset_arrived(line.asset, location, user, order)
        else:
            stock.add(line.part, quantity, location, user, kind=Movement.Kind.RECEIVED, reference=order.number,
                      url=order.get_absolute_url())
        OrderLine.objects.filter(pk=line.pk).update(received=F('received') + quantity)
        booked.append(f'{quantity.normalize():f} × {line.item.number}')
    if not booked:
        raise ValidationError('Fill in what arrived.')
    complete = not any(line.outstanding for line in order.lines.all())
    order.status = Order.Status.RECEIVED if complete else Order.Status.PARTLY
    order.received_on = date.today() if complete else None
    order.save(update_fields=['status', 'received_on'])
    if order.created_by and order.created_by != user:
        notify([order.created_by], f'{order} ({order.vendor}): {", ".join(booked)} arrived'
               + ('; it is complete.' if complete else '.'), order.get_absolute_url())
    return booked


def _asset_arrived(asset, location, user, order):
    """An asset ordered arrived: available, kept at ``location``."""
    from assets.models import Asset, AssetEvent
    Asset.objects.filter(pk=asset.pk).update(status=Asset.Status.AVAILABLE, location=location)
    AssetEvent.objects.create(asset=asset, kind=AssetEvent.Kind.RECEIVED, user=user, note=f'{order.number}, kept at {location.path}')


def cancel(order, user):
    if order.status in (Order.Status.RECEIVED, Order.Status.CANCELLED):
        raise ValidationError(f'{order} is {order.get_status_display().lower()}.')
    if order.lines.filter(received__gt=0).exists():
        raise ValidationError(f'Part of {order} has arrived: it can\'t be cancelled any more.')
    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status'])
    if order.kind == Order.Kind.REQUEST and order.created_by and order.created_by != user:
        notify([order.created_by], f'{user} won\'t order what you asked for ({order}).', order.get_absolute_url())
