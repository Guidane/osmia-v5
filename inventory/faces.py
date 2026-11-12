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


def around(n, centre=False, numbers=None, sweep=360, turn=-90):
    """A round face: ``n`` contacts on a ring (``sweep`` degrees of it, from ``turn``), the last one in the middle
    when ``centre``; ``numbers`` in the order they sit along the ring."""
    on_ring = n - 1 if centre else n
    numbers = numbers or _numbers(n)
    ring = max(PITCH * on_ring / (2 * math.pi) * 360 / sweep, 26)
    step = sweep / (on_ring if sweep == 360 else max(on_ring - 1, 1))
    out = [[numbers[i], ring * math.cos(math.radians(turn + i * step)), ring * math.sin(math.radians(turn + i * step))] for i in range(on_ring)]
    if centre:
        out.append([numbers[-1], 0, 0])
    return fitted('circle', out)


def _terminal(outline, contacts=(('1', 0, 0),)):
    return _custom([list(c) for c in contacts], outline)


def ring_terminal(stud):
    """A ring terminal for an M``stud`` stud: the ring round its contact, the barrel below."""
    r, a = 20 + stud, math.degrees(math.asin(9 / (20 + stud)))
    arc = [[round(r * math.cos(math.radians(t)), 1), round(r * math.sin(math.radians(t)), 1)]
           for t in [90 + a + i * (360 - 2 * a) / 16 for i in range(17)]]
    return _terminal(arc + [[9, r + 8], [9, r + 44], [-9, r + 44], [-9, r + 8]])


def fork_terminal(stud):
    """A fork (spade) terminal for an M``stud`` stud: two tines either side of its contact, the barrel below."""
    gap, tine = 12 + stud // 2, 10
    o = gap + tine
    return _terminal([[-o, -26], [-gap, -26], [-gap, 10], [gap, 10], [gap, -26], [o, -26], [o, 20], [9, 28], [9, 64],
                      [-9, 64], [-9, 28], [-o, 20]])


def flat_terminal(width):
    """A flat (blade, "knife") terminal ``width`` mm wide: the tab (pin side) or its receptacle (socket side)."""
    half = 12 + width
    return _terminal([[-half, -40], [half, -40], [half, 16], [9, 26], [9, 62], [-9, 62], [-9, 26], [-half, 16]])


def bullet_terminal():
    return _terminal([[0, -36], [13, -20], [13, 18], [9, 26], [9, 60], [-9, 60], [-9, 26], [-13, 18], [-13, -20]])


def ferrule():
    return _terminal([[-13, -44], [13, -44], [13, 18], [18, 18], [18, 40], [-18, 40], [-18, 18], [-13, 18]])


def butt_splice():
    return _terminal([[-22, -15], [74, -15], [74, 15], [-22, 15]], (('1', 0, 0), ('2', 52, 0)))


# Connectors made often, each a family: key: (branch, "Parent › Child" for one under another; label; its face; whether
# it has a pin and a socket side)
def _p(group, label, face, genders=True):
    return (group, label, face, genders)


PRESETS = {
    'dsub-9': _p('D-sub', 'D-sub 9 (DE-9)', lambda: rows('dsub', [5, 4], [0, 0.5])),
    'dsub-15': _p('D-sub', 'D-sub 15 (DA-15)', lambda: rows('dsub', [8, 7], [0, 0.5])),
    'dsub-25': _p('D-sub', 'D-sub 25 (DB-25)', lambda: rows('dsub', [13, 12], [0, 0.5])),
    'dsub-37': _p('D-sub', 'D-sub 37 (DC-37)', lambda: rows('dsub', [19, 18], [0, 0.5])),
    'dsub-50': _p('D-sub', 'D-sub 50 (DD-50)', lambda: rows('dsub', [17, 16, 17], [0, 0.5, 0])),
    'hd-15': _p('D-sub HD', 'D-sub HD 15 (DE-15)', lambda: rows('dsub', [5, 5, 5], [0.5, 0, 0.5])),
    'hd-26': _p('D-sub HD', 'D-sub HD 26 (DA-26)', lambda: rows('dsub', [9, 9, 8], [0, 0.5, 1])),
    'hd-44': _p('D-sub HD', 'D-sub HD 44 (DB-44)', lambda: rows('dsub', [15, 15, 14], [0, 0.5, 1])),
    'hd-62': _p('D-sub HD', 'D-sub HD 62 (DC-62)', lambda: rows('dsub', [21, 21, 20], [0, 0.5, 1])),
    'hd-78': _p('D-sub HD', 'D-sub HD 78 (DD-78)', lambda: rows('dsub', [20, 19, 20, 19], [0, 0.5, 0, 0.5])),
    **{f'gecko-{n}': _p('Gecko', f'Gecko {n}', lambda n=n: gecko(n)) for n in (4, 6, 8, 10, 12, 16, 20, 26, 34, 50)},
    # round
    'm8-3': _p('Circular › M8', 'M8 3-pin', lambda: around(3, numbers=['1', '4', '3'], turn=-150, sweep=240)),
    'm8-4': _p('Circular › M8', 'M8 4-pin', lambda: around(4, numbers=['1', '2', '3', '4'], turn=-135)),
    'm8-8': _p('Circular › M8', 'M8 8-pin', lambda: around(8, centre=True)),
    'm12-4': _p('Circular › M12', 'M12 4-pin', lambda: around(4, turn=-135)),
    'm12-5': _p('Circular › M12', 'M12 5-pin', lambda: around(5, centre=True, turn=-135)),
    'm12-8': _p('Circular › M12', 'M12 8-pin', lambda: around(8, centre=True)),
    'm12-12': _p('Circular › M12', 'M12 12-pin', lambda: around(12, centre=True)),
    'xlr-3': _p('Circular › XLR', 'XLR 3', lambda: around(3, numbers=['2', '1', '3'], turn=-150, sweep=240)),
    'xlr-4': _p('Circular › XLR', 'XLR 4', lambda: around(4, turn=-135)),
    'xlr-5': _p('Circular › XLR', 'XLR 5', lambda: around(5, turn=-162)),
    'din-5': _p('Circular › DIN', 'DIN 5 (180°)', lambda: around(5, numbers=['1', '4', '2', '5', '3'], sweep=180, turn=180)),
    'din-6': _p('Circular › DIN', 'DIN 6 (240°)', lambda: around(6, centre=True, numbers=['1', '4', '2', '5', '3', '6'], sweep=240, turn=150)),
    'din-8': _p('Circular › DIN', 'DIN 8 (262°)', lambda: around(8, centre=True, numbers=['6', '1', '4', '2', '5', '3', '7', '8'], sweep=262, turn=139)),
    # rectangular
    **{f'header-{n}': _p('Rectangular › Pin header 2.54', f'Pin header {n}', lambda n=n: start('row', n)) for n in (2, 3, 4, 5, 6, 8, 10, 12, 16, 20)},
    **{f'idc-{n}': _p('Rectangular › IDC 2.54', f'IDC {n}', lambda n=n: rows('rect', [n // 2, n // 2], [0, 0], 'zigzag'))
       for n in (6, 10, 14, 16, 20, 26, 34, 40, 50)},
    **{f'jst-xh-{n}': _p('Rectangular › JST XH', f'JST XH {n}', lambda n=n: start('row', n)) for n in (2, 3, 4, 5, 6, 8, 10, 12)},
    **{f'jst-ph-{n}': _p('Rectangular › JST PH', f'JST PH {n}', lambda n=n: start('row', n)) for n in (2, 3, 4, 5, 6, 8, 10, 12)},
    **{f'kk-{n}': _p('Rectangular › Molex KK 254', f'Molex KK {n}', lambda n=n: start('row', n)) for n in (2, 3, 4, 5, 6, 8)},
    **{f'microfit-{n}': _p('Rectangular › Molex Micro-Fit 3.0', f'Micro-Fit {n}', lambda n=n: start('rows', n) if n > 2 else start('row', n))
       for n in (2, 4, 6, 8, 10, 12, 16, 20, 24)},
    **{f'minifit-{n}': _p('Rectangular › Molex Mini-Fit Jr', f'Mini-Fit {n}', lambda n=n: start('rows', n) if n > 2 else start('row', n))
       for n in (2, 4, 6, 8, 10, 12, 16, 20, 24)},
    'rj12': _p('Rectangular › Modular', 'RJ12 (6P6C)', lambda: start('row', 6)),
    'rj45': _p('Rectangular › Modular', 'RJ45 (8P8C)', lambda: start('row', 8)),
    'usb-a': _p('Rectangular › USB', 'USB A', lambda: start('row', 4)),
    # terminals: one contact each
    **{f'ring-m{n}': _p('Terminals › Ring', f'Ring terminal M{n}', lambda n=n: ring_terminal(n), False) for n in (3, 4, 5, 6, 8)},
    **{f'fork-m{n}': _p('Terminals › Fork', f'Fork terminal M{n}', lambda n=n: fork_terminal(n), False) for n in (3, 4, 5, 6)},
    **{f'flat-{w}': _p('Terminals › Flat (blade)', f'Flat terminal {w}', lambda w=w: flat_terminal(float(w)))
       for w in ('2.8', '4.8', '6.3')},
    'bullet': _p('Terminals', 'Bullet terminal', bullet_terminal),
    'ferrule': _p('Terminals', 'Ferrule', ferrule, False),
    'butt-splice': _p('Terminals', 'Butt splice', butt_splice, False),
}


def preset(key):
    """The face of a connector made often (``PRESETS``); None for a key it doesn't know. A terminal of one kind (a
    ring, a fork) says so: ``'genders': False`` (no pin and socket side to pick)."""
    if key not in PRESETS:
        return None
    face = PRESETS[key][2]()
    return face if PRESETS[key][3] else dict(face, genders=False)


def natural(name):
    """A sort key that puts numbers in their order: Gecko 4 before Gecko 10."""
    import re
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', str(name))]


def family_name(key):
    """The family a connector made often becomes: "D-sub 25", "D-sub HD 44", "Gecko 10", "Ring terminal M4"."""
    label = PRESETS[key][1]
    return label if label.startswith('RJ') else label.split(' (')[0]


def _branch(path):
    """The family branch of ``path`` ("Circular › M12"), made where missing."""
    from .models import FamilyBranch
    node = None
    for name in path.split(' › '):
        node = FamilyBranch.objects.filter(parent=node, name__iexact=name).first() or FamilyBranch.objects.create(name=name, parent=node)
    return node


def standard_families():
    """Every connector made often as a family, in its branch (D-sub, Circular › M12, Terminals › Fork, …), with its face
    and (but for a terminal of one kind: a ring, a fork) its pin and socket genders. One there already (by name, any case) is kept: only what it lacks (a branch, a face, a gender)
    is filled in. Returns how many families were made."""
    from django.db import transaction

    from .models import Branch, Family
    made = 0
    with transaction.atomic():
        for key, (group, _, _, genders) in PRESETS.items():
            branch = _branch(group)
            family = Family.objects.filter(name__iexact=family_name(key)).first()
            if family is None:
                family = Family.objects.create(name=family_name(key), group=branch, face=preset(key))
                made += 1
            else:
                family.group = family.group or branch
                family.face = family.face if (family.face or {}).get('contacts') else preset(key)
                family.save(update_fields=['group', 'face'])
            for side in ('pin', 'socket') if genders else ():
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
