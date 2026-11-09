"""A connector's face as you look at it, defined on its family: an outline (``rect``, ``dsub``, ``circle``, or
``custom``: its corners in ``outline``, [[x, y], ...]) and where each contact sits,
``{'shape', 'w', 'h', 'contacts': [[number, x, y], ...], 'outline': [...]}`` (in the drawing's units: contacts are
``PITCH`` apart, ``R`` their radius). Ready-made ones to start from (a row, two rows, a D-sub, a circle, a grid); the
socket side's face is the pin side's mirrored; what a drawing needs when a connector's pins aren't all on its face."""
import math

PITCH, R, MARGIN = 26, 10, 16   # contacts sit on a grid of half the pitch, from the outline
SHAPES = [('rect', 'Rectangle'), ('dsub', 'D-sub'), ('circle', 'Round'), ('custom', 'Custom')]
STARTS = [('row', 'Single row'), ('rows', 'Two rows'), ('staggered', 'D-sub (two rows, staggered)'), ('circle', 'Round'),
          ('grid', 'Grid')]
CONTACTS = [('pin', 'Pins'), ('socket', 'Sockets')]


def _numbers(n):
    return [str(i) for i in range(1, n + 1)]


def _custom(contacts, outline):
    """A face with an outline of its own: everything moved (by whole grid steps) to start at 0, the size what both take."""
    step = PITCH / 2
    xs = [p[0] for p in outline] + [c[1] - R - 4 for c in contacts]
    ys = [p[1] for p in outline] + [c[2] - R - 4 for c in contacts]
    dx, dy = math.ceil(-min(xs) / step) * step, math.ceil(-min(ys) / step) * step
    w = max([p[0] for p in outline] + [c[1] + R + 4 for c in contacts]) + dx
    h = max([p[1] for p in outline] + [c[2] + R + 4 for c in contacts]) + dy
    return {'shape': 'custom', 'w': round(w, 1), 'h': round(h, 1),
            'contacts': [[str(n), round(x + dx, 1), round(y + dy, 1)] for n, x, y in contacts],
            'outline': [[round(x + dx, 1), round(y + dy, 1)] for x, y in outline]}


def fitted(shape, contacts, outline=None):
    """The face with its outline fitted around the contacts (moved to start at the margin); a custom outline as drawn."""
    if shape == 'custom' and outline and len(outline) >= 3:
        return _custom(contacts, outline)
    shape = 'rect' if shape == 'custom' else shape
    if not contacts:
        return {'shape': shape, 'w': 2 * (MARGIN + R), 'h': 2 * (MARGIN + R), 'contacts': []}
    xs, ys = [c[1] for c in contacts], [c[2] for c in contacts]
    dx, dy = MARGIN + R - min(xs), MARGIN + R - min(ys)
    w, h = max(xs) - min(xs) + 2 * (MARGIN + R), max(ys) - min(ys) + 2 * (MARGIN + R)
    if shape == 'circle':
        side = max(w, h)
        dx, dy, w, h = dx + (side - w) / 2, dy + (side - h) / 2, side, side
    if shape == 'dsub':   # room for the slanted sides
        dx, w = dx + PITCH / 2, w + PITCH
    return {'shape': shape, 'w': round(w, 1), 'h': round(h, 1),
            'contacts': [[str(n), round(x + dx, 1), round(y + dy, 1)] for n, x, y in contacts]}


def start(kind, positions, columns=None):
    """A ready-made face of ``positions`` contacts numbered from 1."""
    n = max(int(positions or 0), 1)
    numbers = _numbers(n)
    if kind == 'staggered':   # a D-sub: the first half along the wide side, the rest between them below
        half = math.ceil(n / 2)
        return fitted('dsub', [[p, i * PITCH if i < half else (i - half + 0.5) * PITCH, 0 if i < half else PITCH]
                               for i, p in enumerate(numbers)])
    if kind == 'rows':
        half = math.ceil(n / 2)
        return fitted('rect', [[p, (i % half) * PITCH, (i // half) * PITCH] for i, p in enumerate(numbers)])
    if kind == 'circle':
        ring = max(PITCH * n / (2 * math.pi), 22)
        return fitted('circle', [[p, ring * math.cos(-math.pi / 2 + 2 * math.pi * i / n), ring * math.sin(-math.pi / 2 + 2 * math.pi * i / n)]
                                 for i, p in enumerate(numbers)])
    if kind == 'grid':
        cols = int(columns or 0) or math.ceil(math.sqrt(n))
        return fitted('rect', [[p, (i % cols) * PITCH, (i // cols) * PITCH] for i, p in enumerate(numbers)])
    return fitted('rect', [[p, i * PITCH, 0] for i, p in enumerate(numbers)])


def rows(shape, counts, offsets, numbering='rows'):
    """Contacts in rows (``counts`` of each, top first), each row moved by its ``offsets`` (in pitches); numbered row
    by row from the top left, or ``zigzag``: 1 top, 2 below it, 3 top, … (two rows)."""
    if numbering == 'zigzag':
        n = sum(counts)
        return fitted(shape, [[str(i + 1), (i // 2) * PITCH, (i % 2) * PITCH] for i in range(n)])
    out, number = [], 1
    for r, (count, offset) in enumerate(zip(counts, offsets)):
        for i in range(count):
            out.append([str(number), (i + offset) * PITCH, r * PITCH])
            number += 1
    return fitted(shape, out)


def gecko(n):
    """A Gecko of ``n`` contacts (as drawn for gecko 6): two rows, numbered along the top row and then the bottom one;
    a box with a notch at each top corner and a key in the middle of the bottom."""
    cols, step = n // 2, PITCH / 2
    w, top, low = PITCH * (cols + 1), step, 7 * step
    contacts = [[str(i + 1), PITCH * (i % cols + 1), 3 * step + (i // cols) * PITCH] for i in range(n)]
    mid = w / 2
    outline = [[0, top], [0, 0], [step, 0], [step, top], [w - step, top], [w - step, 0], [w, 0], [w, low],
               [mid + step, low], [mid + step, low + 2 * step], [mid - step, low + 2 * step], [mid - step, low], [0, low]]
    return _custom(contacts, outline)


# Connectors made often: (group, label, rows top first, each row moved by, numbering)
PRESETS = {
    'dsub-9': ('D-sub', 'D-sub 9 (DE-9)', [5, 4], [0, 0.5]),
    'dsub-15': ('D-sub', 'D-sub 15 (DA-15)', [8, 7], [0, 0.5]),
    'dsub-25': ('D-sub', 'D-sub 25 (DB-25)', [13, 12], [0, 0.5]),
    'dsub-37': ('D-sub', 'D-sub 37 (DC-37)', [19, 18], [0, 0.5]),
    'dsub-50': ('D-sub', 'D-sub 50 (DD-50)', [17, 16, 17], [0, 0.5, 0]),
    'hd-15': ('D-sub HD', 'D-sub HD 15 (DE-15)', [5, 5, 5], [0.5, 0, 0.5]),
    'hd-26': ('D-sub HD', 'D-sub HD 26 (DA-26)', [9, 9, 8], [0, 0.5, 1]),
    'hd-44': ('D-sub HD', 'D-sub HD 44 (DB-44)', [15, 15, 14], [0, 0.5, 1]),
    'hd-62': ('D-sub HD', 'D-sub HD 62 (DC-62)', [21, 21, 20], [0, 0.5, 1]),
    'hd-78': ('D-sub HD', 'D-sub HD 78 (DD-78)', [20, 19, 20, 19], [0, 0.5, 0, 0.5]),
    **{f'gecko-{n}': ('Gecko', f'Gecko {n}', [n // 2, n // 2], [0, 0]) for n in (4, 6, 8, 10, 12, 16, 20, 26, 34, 50)},
}


def preset(key):
    """The face of a connector made often (``PRESETS``); None for a key it doesn't know."""
    if key not in PRESETS:
        return None
    group, _, counts, offsets, *numbering = PRESETS[key]
    if group == 'Gecko':
        return gecko(sum(counts))
    return rows('dsub', counts, offsets, *numbering)


def natural(name):
    """A sort key that puts numbers in their order: Gecko 4 before Gecko 10."""
    import re
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', str(name))]


def family_name(key):
    """The family a connector made often becomes: "D-sub 25", "D-sub HD 44", "Gecko 10"."""
    return PRESETS[key][1].split(' (')[0]


def standard_families():
    """Every connector made often as a family, in its branch (D-sub, D-sub HD, Gecko), with its face and its pin and
    socket genders. One there already (by name, any case) is kept: only what it lacks (a branch, a face, a gender)
    is filled in. Returns how many families were made."""
    from django.db import transaction

    from .models import Branch, Family, FamilyBranch
    made = 0
    with transaction.atomic():
        for key, (group, *_rest) in PRESETS.items():
            branch = FamilyBranch.objects.filter(parent=None, name__iexact=group).first() or FamilyBranch.objects.create(name=group)
            family = Family.objects.filter(name__iexact=family_name(key)).first()
            if family is None:
                family = Family.objects.create(name=family_name(key), group=branch, face=preset(key))
                made += 1
            else:
                family.group = family.group or branch
                family.face = family.face if (family.face or {}).get('contacts') else preset(key)
                family.save(update_fields=['group', 'face'])
            for side in ('pin', 'socket'):
                if not family.branches.filter(contacts=side).exists() and not family.branches.filter(name__iexact=side).exists():
                    Branch.objects.create(family=family, name=side, contacts=side)
    return made


def preset_choices():
    """For the editor's list: [(group, [(key, label)])]."""
    groups = {}
    for key, (group, label, *_) in PRESETS.items():
        groups.setdefault(group, []).append((key, label))
    return list(groups.items())


def mirrored(face):
    out = dict(face, contacts=[[n, round(face['w'] - x, 1), y] for n, x, y in face['contacts']])
    if face.get('outline'):
        out['outline'] = [[round(face['w'] - x, 1), y] for x, y in face['outline']]
    return out


def face_of(found):
    """The face of a part, a branch or a family (their family's; mirrored for sockets); None when it has none."""
    family = found if found is not None and type(found).__name__ == 'Family' else getattr(found, 'family', None)
    if family is None or not (family.face or {}).get('contacts'):
        return None
    branch = found if type(found).__name__ == 'Branch' else getattr(found, 'branch', None)
    return mirrored(family.face) if branch is not None and branch.contacts == 'socket' else family.face


def drawn(found, numbers):
    """The face to draw for a connector whose pins are ``numbers``: its family's, with any pin not on it in a row
    below; without one, a row of its pins (every number up to the highest, when they are numbers)."""
    face = face_of(found)
    if face is None:
        if numbers and all(n.isdigit() for n in numbers):
            numbers = _numbers(max(int(n) for n in numbers))
        return fitted('rect', [[p, i * PITCH, 0] for i, p in enumerate(numbers)])
    on = {c[0] for c in face['contacts']}
    extra = [n for n in numbers if n not in on]
    if not extra:
        return face
    y = face['h'] + R + 6
    return dict(face, h=y + R + MARGIN, contacts=face['contacts'] + [[p, MARGIN + R + i * PITCH, y] for i, p in enumerate(extra)],
                below=face['h'], w=max(face['w'], 2 * (MARGIN + R) + (len(extra) - 1) * PITCH))
