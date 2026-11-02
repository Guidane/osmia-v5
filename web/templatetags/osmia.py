from decimal import Decimal

from django import template

register = template.Library()


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
def document_button(thing):
    """A button to the documentation page of a part, asset, device, harness or project."""
    from django.utils.html import format_html

    from web.documents import url_of
    return format_html('<a class="btn" href="{}">📄 Documentation</a>', url_of(thing))


@register.simple_tag
def document_image(thing):
    """The picture of a part, asset, device, harness or project (from its documentation), if it has one."""
    from django.urls import reverse
    from django.utils.html import format_html

    from web.documents import document_of, kind_of, url_of
    doc = document_of(thing)
    if doc is None or not doc.image:
        return ''
    return format_html('<a class="main-image" href="{}"><img src="{}" alt="{}"></a>', url_of(thing),
                       reverse('web:image', args=[kind_of(thing), thing.pk]), str(thing))


@register.filter
def markup(text):
    """Documentation, cleaned (see web.markup)."""
    from web.markup import render
    return render(text)
