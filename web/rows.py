"""Editing records as rows of a table, in one form: each row's inputs are named ``r<n>_<column>``, ``r<n>_id`` its
record (none for a new row) and ``r<n>_gone`` ticked to take it away. See ``web/_rows.html``."""


class Column:
    def __init__(self, name, label, kind='text', options=(), datalist='', width=''):
        self.name, self.label, self.kind, self.options, self.datalist, self.width = name, label, kind, options, datalist, width


def rows(records, values, blank=3):
    """The rows a form shows: [{"prefix", "id", "values"}] for ``records`` (``values(record)``: {column: value}),
    then ``blank`` empty ones."""
    out = [{'prefix': f'r{i}', 'id': r.pk, 'values': values(r)} for i, r in enumerate(records)]
    return out + [{'prefix': f'r{n}', 'id': None, 'values': {}} for n in range(len(out), len(out) + blank)]


def read(post, columns):
    """What the form sent: [(row number, record id or None, gone, {column: text})], skipping empty new rows."""
    out, n = [], 0
    while f'r{n}_seen' in post:
        values = {c.name: (post.get(f'r{n}_{c.name}') or '').strip() if c.kind != 'check' else f'r{n}_{c.name}' in post
                  for c in columns}
        row_id = post.get(f'r{n}_id')
        row_id = int(row_id) if row_id and row_id.isdigit() else None
        if row_id or any(v for v in values.values()):
            out.append((n + 1, row_id, bool(post.get(f'r{n}_gone')), values))
        n += 1
    return out
