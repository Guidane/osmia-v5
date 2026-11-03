"""The only way stock changes: each function changes the quantities and keeps a Movement. Quantities never go
below zero."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Movement, Stock


def amount(value, allow_zero=False):
    """A quantity from a form: a positive number (or zero, if ``allow_zero``)."""
    try:
        n = Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, AttributeError):
        raise ValidationError(f'"{value}" is not a number.')
    if not n.is_finite() or n < 0 or (n == 0 and not allow_zero):
        raise ValidationError('Give a quantity above zero.' if not allow_zero else 'Give a quantity of zero or more.')
    return n


def _row(part, location):
    row, _ = Stock.objects.select_for_update().get_or_create(part=part, location=location)
    return row


def _take(part, location, quantity):
    row = _row(part, location)
    if row.quantity < quantity:
        raise ValidationError(f'There are only {Decimal(row.quantity).normalize():f} {part.unit} of {part} in {location}.')
    row.quantity -= quantity
    row.save(update_fields=['quantity'])


def _put(part, location, quantity):
    row = _row(part, location)
    row.quantity += quantity
    row.save(update_fields=['quantity'])


@transaction.atomic
def add(part, quantity, location, user, note='', kind=Movement.Kind.ADDED, reference='', url=''):
    """Stock coming in: found, made, or received for an order (``kind`` RECEIVED)."""
    quantity = amount(quantity)
    _put(part, location, quantity)
    return Movement.objects.create(part=part, kind=kind, quantity=quantity, target=location, note=note[:300],
                                   reference=reference, url=url, user=user)


@transaction.atomic
def move(part, quantity, source, target, user, note=''):
    quantity = amount(quantity)
    if source == target:
        raise ValidationError('Pick another location to move it to.')
    _take(part, source, quantity)
    _put(part, target, quantity)
    return Movement.objects.create(part=part, kind=Movement.Kind.MOVED, quantity=quantity, source=source, target=target,
                                   note=note[:300], user=user)


@transaction.atomic
def use(part, quantity, source, user, note=''):
    """Stock going out: used, scrapped, sent away."""
    quantity = amount(quantity)
    _take(part, source, quantity)
    return Movement.objects.create(part=part, kind=Movement.Kind.USED, quantity=quantity, source=source, note=note[:300], user=user)


@transaction.atomic
def use_any(family, quantity, source, user, note=''):
    """Stock of a family (or a branch of one) going out: from the parts of it in ``source``, the most stocked first."""
    quantity = amount(quantity)
    rows = list(Stock.objects.filter(part__in=family.members(), location=source, quantity__gt=0).select_related('part').order_by('-quantity'))
    if sum(r.quantity for r in rows) < quantity:
        raise ValidationError(f'There are only {Decimal(sum(r.quantity for r in rows)).normalize():f} {family.unit} of {family} in {source}.')
    for row in rows:
        taken = min(row.quantity, quantity)
        use(row.part, taken, source, user, note)
        quantity -= taken
        if not quantity:
            break


@transaction.atomic
def count(part, location, quantity, user, note=''):
    """What is really there after counting: the stock becomes ``quantity``; the movement keeps the difference."""
    quantity = amount(quantity, allow_zero=True)
    row = _row(part, location)
    difference = quantity - row.quantity
    row.quantity = quantity
    row.save(update_fields=['quantity'])
    return Movement.objects.create(part=part, kind=Movement.Kind.COUNTED, quantity=difference, target=location,
                                   note=note[:300], user=user)
