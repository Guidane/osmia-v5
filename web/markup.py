"""Documentation is written in the page's editor and kept as HTML. Before it is kept, it is cleaned: only the tags and
attributes of text, headings, lists, tables, links and pictures stay (no scripts, styles, frames or event handlers),
and links and pictures may only point to web pages or within Osmia."""
from html import escape
from html.parser import HTMLParser

from django.utils.safestring import mark_safe

TAGS = {'p', 'br', 'h2', 'h3', 'h4', 'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'sub', 'sup', 'code', 'pre', 'blockquote',
        'ul', 'ol', 'li', 'hr', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'span'}
VOID = {'br', 'hr', 'img'}
ATTRIBUTES = {'a': {'href', 'title'}, 'img': {'src', 'alt', 'width'}, 'th': {'colspan', 'rowspan'}, 'td': {'colspan', 'rowspan'}}
DROP = {'script', 'style', 'iframe', 'object', 'embed', 'head', 'title', 'template'}   # gone with all that is in them


def _safe_url(url):
    url = (url or '').strip()
    return url if url.startswith(('http://', 'https://', 'mailto:', '/')) and not url.startswith('//') else ''


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.open, self.dropping = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP:
            self.dropping += 1
            return
        if self.dropping or tag not in TAGS:
            return
        kept = []
        for name, value in attrs:
            if name in ATTRIBUTES.get(tag, ()):
                if name in ('href', 'src'):
                    value = _safe_url(value)
                    if not value:
                        continue
                if name in ('colspan', 'rowspan', 'width') and not str(value).isdigit():
                    continue
                kept.append(f' {name}="{escape(value or "", quote=True)}"')
        if tag == 'a':
            kept.append(' rel="noopener noreferrer"')
        if tag == 'img' and not any(k.startswith(' src=') for k in kept):
            return
        self.out.append(f'<{tag}{"".join(kept)}>')
        if tag not in VOID:
            self.open.append(tag)

    def handle_endtag(self, tag):
        if tag in DROP:
            self.dropping = max(0, self.dropping - 1)
            return
        if self.dropping or tag not in TAGS or tag in VOID or tag not in self.open:
            return
        while self.open:   # close what was left open inside it
            last = self.open.pop()
            self.out.append(f'</{last}>')
            if last == tag:
                break

    def handle_data(self, data):
        if not self.dropping:
            self.out.append(escape(data, quote=False))


def clean(html):
    """``html`` with only what documentation may hold."""
    cleaner = _Cleaner()
    cleaner.feed(html or '')
    cleaner.close()
    return ''.join(cleaner.out + [f'</{t}>' for t in reversed(cleaner.open)])


def render(html):
    """Kept documentation, to show (cleaned again, in case it was put in some other way)."""
    return mark_safe(clean(html))
