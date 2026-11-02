"""Excel export: sheets of rows as an .xlsx download."""
from io import BytesIO

from django.http import HttpResponse
from django.utils.text import slugify


def download(filename, sheets):
    """``sheets``: [(title, headers, rows)]. Rows hold plain values (text, numbers, dates)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    book = Workbook()
    book.remove(book.active)
    for title, headers, rows in sheets:
        sheet = book.create_sheet(_title(title))
        sheet.append(list(headers))
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        widths = [len(str(h)) for h in headers]
        for row in rows:
            row = [_plain(v) for v in row]
            sheet.append(row)
            widths = [max(w, len(str(v or ''))) for w, v in zip(widths, row)] + widths[len(row):]
        for i, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 8), 60)
        sheet.freeze_panes = 'A2'
    if not book.sheetnames:
        book.create_sheet('Empty')
    out = BytesIO()
    book.save(out)
    response = HttpResponse(out.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{slugify(filename) or "osmia"}.xlsx"'
    return response


def _title(text):
    """A sheet name Excel accepts: at most 31 characters, none of the characters it refuses."""
    for ch in '[]:*?/\\':
        text = text.replace(ch, ' ')
    return text[:31] or 'Sheet'


def _plain(value):
    from datetime import datetime
    from decimal import Decimal

    from django.utils import timezone
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime) and timezone.is_aware(value):   # Excel keeps no time zones
        return timezone.localtime(value).replace(tzinfo=None)
    if value is None or isinstance(value, (str, int, float)) or hasattr(value, 'isoformat'):
        return value
    return str(value)
