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
