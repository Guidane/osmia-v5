from decimal import Decimal

from django import template

register = template.Library()


@register.simple_tag
def fresh(path):
    """The URL of a static file with when it last changed, so browsers fetch it again after a change or an update."""
    import os

    from django.contrib.staticfiles import finders
    from django.templatetags.static import static
    url = static(path)
    if 'v=' in url:   # the static storage gave it its version already
        return url
    found = finders.find(path)
    return f'{url}?v={int(os.path.getmtime(found))}' if found else url


@register.filter
def qty(value):
    """A quantity without trailing zeros: 10, 2.5, 0.125 (never 1E+1)."""
    if value in (None, ''):
        return ''
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    text = f'{value.normalize():f}'
    return '0' if text in ('-0', '0') else text


@register.filter
def get_item(mapping, key):
    return (mapping or {}).get(key)


@register.filter
def mul(value, by):
    return value * by


@register.filter
def sub(value, minus):
    return value - minus


@register.filter
def money(value):
    """An amount: 1,234.50 (with the OSMIA_CURRENCY symbol before it, if set)."""
    from django.conf import settings
    if value in (None, ''):
        return ''
    value = Decimal(str(value))
    text = f'{abs(value):,.2f}'
    symbol = getattr(settings, 'OSMIA_CURRENCY', '')
    return f'{"-" if value < 0 else ""}{symbol}{text}'


@register.filter
def money_abs(value):
    return money(abs(Decimal(str(value)))) if value not in (None, '') else ''


@register.simple_tag
def preview(thing):
    """The preview picture of a thing (one of its files), if it has one."""
    from django.urls import reverse
    from django.utils.html import format_html

    from web.things import preview_of
    shown = preview_of(thing)
    if shown is None:
        return ''
    url = reverse('web:file', args=[shown.pk])
    return format_html('<a class="main-image" href="{}" target="_blank"><img src="{}" alt="{}"></a>', url, url, str(thing))


@register.simple_tag(takes_context=True)
def thumb(context, thing):
    """A small preview picture of a thing in a list (an empty square when it has none). The previews of a kind are
    looked up once per page."""
    from django.contrib.contenttypes.models import ContentType
    from django.urls import reverse
    from django.utils.html import format_html

    from web.models import Attachment
    ct = ContentType.objects.get_for_model(thing)
    cache = context.render_context.setdefault('osmia_thumbs', {})
    if ct.pk not in cache:
        cache[ct.pk] = dict(Attachment.objects.filter(content_type=ct, preview=True).values_list('object_id', 'pk'))
    found = cache[ct.pk].get(thing.pk)
    if found is None:
        return format_html('<span class="thumb-sm empty"></span>')
    return format_html('<img class="thumb-sm" src="{}" alt="" loading="lazy">', reverse('web:file', args=[found]))


@register.inclusion_tag('web/_side.html', takes_context=True)
def side(context, thing):
    """The Files and Documentation cards of a thing."""
    from web.things import files_of, kind_of, pages_of
    return {'thing': thing, 'kind': kind_of(thing), 'files': files_of(thing), 'pages': pages_of(thing),
            'request': context.get('request'), 'csrf_token': context.get('csrf_token')}


@register.filter
def ext(name):
    """A file's kind, from its name: PDF, DOCX, …"""
    return name.rsplit('.', 1)[-1].upper()[:5] if '.' in name else 'FILE'


@register.filter
def markup(text):
    """Documentation, cleaned (see web.markup)."""
    from web.markup import render
    return render(text)


@register.filter
def kind(obj):
    """What ``obj`` is called in addresses (``web.things``): part, asset, harness, …"""
    from web.things import kind_of
    return kind_of(obj)
