"""The family popup (``inventory/static/inventory/family_picker.js``): the branches of families as a tree, each family
with its face and its genders. Used where a connector's family is picked: a device connector's form, a harness's
drawing. A gender picked that its family hasn't got yet (pin, socket) is made with ``with_gender``."""
from django.utils.html import format_html, json_script

from web.templatetags.osmia import fresh

from .faces import face_of, natural
from .models import Branch, Family, FamilyBranch


def genders(family):
    """A family's genders to pick from: its own, and pin and socket when it has none of that side yet (and has sides:
    a ring terminal hasn't)."""
    own = list(family.branches.all())
    out = [{'name': b.name, 'value': b.number, 'socket': b.contacts == 'socket'} for b in own]
    sides = {b.contacts for b in own} | {b.name.lower() for b in own}
    for side in ('pin', 'socket') if (family.face or {}).get('genders', True) else ():   # (not for a ring terminal)
        if side not in sides:
            out.append({'name': side, 'value': f'{family.name} / {side}', 'socket': side == 'socket'})
    return out


def data():
    families = [{'name': f.name, 'face': face_of(f), 'branch': f.group_id, 'genders': genders(f)}
                for f in sorted(Family.objects.prefetch_related('branches'), key=lambda f: natural(f.name))]
    tree = [{'id': b.pk, 'name': b.name, 'depth': depth, 'below': sorted(b.below())} for b, depth in FamilyBranch.ordered()]
    return {'families': families, 'tree': tree}


def dialog():
    """The popup, its data and its scripts, once on a page."""
    return format_html(
        '<dialog class="finder family-finder" aria-label="Family"><div class="finder-head"><h3>Family</h3>'
        '<input type="search" data-family-q placeholder="Search" aria-label="Search" autocomplete="off">'
        '<span class="spacer"></span><button type="button" class="btn small ghost" data-family-close title="Close">✕</button></div>'
        '<div class="finder-body"><nav class="finder-tree" data-family-tree aria-label="Branches"></nav>'
        '<div class="family-cards" data-family-cards></div></div></dialog>{}'
        '<script src="{}"></script><script src="{}"></script>',
        json_script(data(), 'family-data'), fresh('harnesses/pinout.js'), fresh('inventory/family_picker.js'))


def with_gender(text):
    """``text`` as it was picked; "<family> / pin" or "/ socket" makes that gender when the family hasn't one."""
    text = (text or '').strip()
    family, _, side = text.rpartition(' / ')
    if family and side.lower() in ('pin', 'socket'):
        found = Family.objects.filter(name__iexact=family.strip()).first()
        if found and not found.branches.filter(name__iexact=side).exists():
            Branch.objects.create(family=found, name=side.lower(), contacts=side.lower())
    return text
