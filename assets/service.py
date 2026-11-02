"""What happens to assets: checked out and brought back, calibrated, sent away (calibration, repair), retired, put in
use. Each keeps an AssetEvent."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Asset, AssetEvent

AWAY = (Asset.Status.CALIBRATION, Asset.Status.REPAIR, Asset.Status.RETIRED, Asset.Status.IN_USE)


def event(asset, kind, user, note=''):
    return AssetEvent.objects.create(asset=asset, kind=kind, user=user, note=str(note or '').strip()[:300])


def _locked(asset):
    return Asset.objects.select_for_update().get(pk=asset.pk)


@transaction.atomic
def check_out(asset, user, to=None, note=''):
    """``to`` (else ``user``) has the asset now."""
    asset = _locked(asset)
    if asset.status != Asset.Status.AVAILABLE:
        raise ValidationError(f'{asset} is {asset.get_status_display().lower()}' + (f' ({asset.holder})' if asset.holder else '') + '.')
    asset.status, asset.holder = Asset.Status.OUT, to or user
    asset.save(update_fields=['status', 'holder'])
    event(asset, AssetEvent.Kind.OUT, user, f'to {asset.holder}' + (f': {note}' if note else ''))
    return asset


@transaction.atomic
def bring_back(asset, user, note=''):
    """Back where it is kept, from being checked out, in use or sent away."""
    asset = _locked(asset)
    if asset.status in (Asset.Status.AVAILABLE, Asset.Status.RETIRED, Asset.Status.ORDERED, Asset.Status.BUILDING):
        raise ValidationError(f'{asset} is {asset.get_status_display().lower()}.')
    asset.status, asset.holder = Asset.Status.AVAILABLE, None
    asset.save(update_fields=['status', 'holder'])
    event(asset, AssetEvent.Kind.BACK, user, note)
    return asset


@transaction.atomic
def calibrated(asset, user, on=None, note=''):
    """It was calibrated (``on``, else today): due again after its interval. An asset away for calibration is back."""
    asset = _locked(asset)
    on = on or date.today()
    if on > date.today():
        raise ValidationError('A calibration can\'t be in the future.')
    asset.calibrated_on = on
    if asset.status == Asset.Status.CALIBRATION:
        asset.status = Asset.Status.AVAILABLE
    asset.save(update_fields=['calibrated_on', 'status'])
    event(asset, AssetEvent.Kind.CALIBRATED, user, f'on {on:%d %b %Y}' + (f': {note}' if note else ''))
    return asset


@transaction.atomic
def send_away(asset, user, why, note=''):
    """Away for calibration or repair, in use (installed somewhere), or retired (``why``: an Asset.Status)."""
    asset = _locked(asset)
    if why not in AWAY:
        raise ValidationError('Where is it going?')
    if asset.status == Asset.Status.OUT:
        raise ValidationError(f'{asset.holder} has {asset} out: bring it back first.')
    asset.status, asset.holder = why, None
    asset.save(update_fields=['status', 'holder'])
    event(asset, AssetEvent.Kind.AWAY, user, Asset.Status(why).label + (f': {note}' if note else ''))
    return asset


def due(within_days=14):
    """The assets due for calibration within ``within_days`` (and overdue ones), soonest first."""
    limit = date.today() + timedelta(days=within_days)
    found = [a for a in Asset.objects.exclude(status=Asset.Status.RETIRED).exclude(calibration_months=None).select_related('keeper')
             if a.calibration_due <= limit]
    return sorted(found, key=lambda a: a.calibration_due)


def next_tag(prefix):
    """The first free asset tag ``<prefix>-001``, ``<prefix>-002``…"""
    n = Asset.objects.filter(number__startswith=f'{prefix}-').count() + 1
    while Asset.objects.filter(number=f'{prefix}-{n:03d}').exists():
        n += 1
    return f'{prefix}-{n:03d}'
