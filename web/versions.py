"""Saving and restoring versions of a design: a model with ``version`` (the last number saved), ``versions`` (its
Version rows), ``snapshot()`` and ``restore(data)``."""
from django.core.exceptions import ValidationError
from django.db import transaction


def _same(data, now):
    """Whether a saved version is the design as it is now (what an older version didn't keep counts as the same)."""
    return {**{k: v for k, v in now.items() if k not in data}, **data} == now


def changed(design):
    """Whether the design differs from its last saved version (True when none is saved)."""
    last = design.versions.order_by('-number').first()
    return last is None or not _same(last.data, design.snapshot())


@transaction.atomic
def save(design, user, note=''):
    last = design.versions.order_by('-number').first()
    data = design.snapshot()
    if last is not None and _same(last.data, data):
        raise ValidationError(f'Nothing changed since v{last.number}.')
    version = design.versions.create(number=(last.number + 1) if last else 1, note=str(note or '').strip()[:300],
                                     data=data, created_by=user)
    type(design).objects.filter(pk=design.pk).update(version=version.number)
    design.version = version.number
    return version


@transaction.atomic
def restore(design, version):
    """Make the design as it was in ``version``; save a version to keep it."""
    design.restore(version.data)
