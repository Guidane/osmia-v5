"""Where what parts and assets fill in for their attributes is kept: values (PartValue, AssetValue) and links to parts or
assets (PartLink and PartAsset for parts, AssetLink for assets). ``store_for`` gives the one for a part or an asset;
forms, pages and lists use it the same way for both."""
from .models import Attribute, Part, PartLink, PartValue


class Store:
    value_model = None        # (subject, attribute, value, number)
    subject = ''              # the field naming the part or asset on the value and link models

    def values(self, obj):
        """{attribute id: value} of what ``obj`` filled in (not links)."""
        return {v.attribute_id: v.value for v in self.value_model.objects.filter(**{self.subject: obj})}

    def save(self, obj, attributes, values, links):
        """Keep ``values`` ({attribute id: (text, number)}) and ``links`` ({attribute id: [part or asset]}) for ``obj``;
        drop what it had for attributes it no longer has; give it the next auto number of those it has none of yet."""
        kept = [a.pk for a in attributes]
        self.value_model.objects.filter(**{self.subject: obj}).exclude(attribute__in=kept).delete()
        self.drop_links(obj, kept)
        for a in attributes:
            if a.is_link:
                self.set_links(obj, a, links.get(a.pk, []))
                continue
            if a.kind == Attribute.Kind.AUTO:
                number_up(a, [obj])
                continue
            text, number = values.get(a.pk, ('', None))
            if text:
                self.value_model.objects.update_or_create(**{self.subject: obj}, attribute=a, defaults={'value': text, 'number': number})
            else:
                self.value_model.objects.filter(**{self.subject: obj}, attribute=a).delete()

    def matching(self, attribute, **lookup):
        """The pks of the parts or assets whose value for ``attribute`` matches ``lookup`` (e.g. value__iexact=...)."""
        return self.value_model.objects.filter(attribute=attribute, **lookup).values(self.subject)


class PartStore(Store):
    value_model, subject = PartValue, 'part'

    def linked(self, attribute, part):
        if attribute.to_assets:
            from assets.models import Asset
            return list(Asset.objects.filter(part_links__part=part, part_links__attribute=attribute))
        return list(Part.objects.filter(linked_from__part=part, linked_from__attribute=attribute))

    def set_links(self, part, attribute, wanted):
        from assets.models import PartAsset
        model, field = (PartAsset, 'asset') if attribute.to_assets else (PartLink, 'target')
        model.objects.filter(part=part, attribute=attribute).exclude(**{f'{field}__in': wanted}).delete()
        for x in wanted:
            model.objects.get_or_create(part=part, attribute=attribute, **{field: x})

    def drop_links(self, part, kept):
        from assets.models import PartAsset
        PartLink.objects.filter(part=part).exclude(attribute__in=kept).delete()
        PartAsset.objects.filter(part=part).exclude(attribute__in=kept).delete()

    def link_texts(self, parts):
        """{part id: {attribute id: "A-1, B-2"}} of what the parts link to, for lists."""
        from assets.models import PartAsset
        out = {}
        for link in PartLink.objects.filter(part__in=parts).select_related('target'):
            out.setdefault(link.part_id, {}).setdefault(link.attribute_id, []).append(link.target.number)
        for link in PartAsset.objects.filter(part__in=parts).select_related('asset'):
            out.setdefault(link.part_id, {}).setdefault(link.attribute_id, []).append(link.asset.number)
        return {p: {a: ', '.join(n) for a, n in d.items()} for p, d in out.items()}


class AssetStore(Store):
    subject = 'asset'

    @property
    def value_model(self):
        from assets.models import AssetValue
        return AssetValue

    def linked(self, attribute, asset):
        from assets.models import Asset
        if attribute.to_assets:
            return list(Asset.objects.filter(linked_from__asset=asset, linked_from__attribute=attribute))
        return list(Part.objects.filter(linked_from_assets__asset=asset, linked_from_assets__attribute=attribute))

    def set_links(self, asset, attribute, wanted):
        from assets.models import AssetLink
        field = 'target' if attribute.to_assets else 'part'
        AssetLink.objects.filter(asset=asset, attribute=attribute).exclude(**{f'{field}__in': wanted}).delete()
        for x in wanted:
            AssetLink.objects.get_or_create(asset=asset, attribute=attribute, **{field: x})

    def drop_links(self, asset, kept):
        from assets.models import AssetLink
        AssetLink.objects.filter(asset=asset).exclude(attribute__in=kept).delete()

    def link_texts(self, assets):
        from assets.models import AssetLink
        out = {}
        for link in AssetLink.objects.filter(asset__in=assets).select_related('part', 'target'):
            out.setdefault(link.asset_id, {}).setdefault(link.attribute_id, []).append((link.part or link.target).number)
        return {t: {a: ', '.join(n) for a, n in d.items()} for t, d in out.items()}


def number_up(attribute, objs):
    """Give each of ``objs`` (parts or assets) without one the next auto number of ``attribute``, in turn."""
    from django.db import transaction
    with transaction.atomic():
        Attribute.objects.select_for_update().filter(pk=attribute.pk).first()   # one numbering at a time
        number = attribute.next_number()
        for obj in objs:
            store = store_for(obj)
            if not store.value_model.objects.filter(**{store.subject: obj}, attribute=attribute).exists():
                store.value_model.objects.create(**{store.subject: obj}, attribute=attribute, value=attribute.auto_value(number), number=number)
                number += 1


def store_for(obj):
    return PartStore() if isinstance(obj, Part) else AssetStore()


def linked_here(obj):
    """What other parts and assets say of ``obj`` (a part or an asset): {"Mates with pins": [parts and assets]}."""
    from assets.models import AssetLink, PartAsset
    found = {}
    if isinstance(obj, Part):
        links = list(PartLink.objects.filter(target=obj).select_related('part', 'attribute__category'))
        links += list(AssetLink.objects.filter(part=obj).select_related('asset', 'attribute__category'))
    else:
        links = list(PartAsset.objects.filter(asset=obj).select_related('part', 'attribute__category'))
        links += list(AssetLink.objects.filter(target=obj).select_related('asset', 'attribute__category'))
    for link in links:
        source = link.part if isinstance(link, (PartLink, PartAsset)) else link.asset
        found.setdefault(link.attribute.other_side(), []).append(source)
    return sorted(found.items())


def filtered(found, attributes, query, store):
    """``found`` (parts or assets) narrowed to those whose attributes match what a list is filtered by: a<id> (text:
    contains; a choice or yes/no: is), a<id>_min and a<id>_max (numbers)."""
    from decimal import Decimal, InvalidOperation
    for a in (a for a in attributes if not a.is_link):
        wanted = query.get(f'a{a.pk}', '').strip()
        if wanted and a.kind not in Attribute.NUMERIC:
            exact = a.kind in (Attribute.Kind.CHOICE, Attribute.Kind.YESNO)
            found = found.filter(pk__in=store.matching(a, **({'value__iexact': wanted} if exact else {'value__icontains': wanted})))
        for end, lookup in (('min', 'number__gte'), ('max', 'number__lte')):
            text = query.get(f'a{a.pk}_{end}', '').strip().replace(',', '.')
            if text and a.kind in Attribute.NUMERIC:
                try:
                    found = found.filter(pk__in=store.matching(a, **{lookup: Decimal(text)}))
                except InvalidOperation:
                    pass
    return found


def columns(objs, attributes, store):
    """[(obj, [shown value of each attribute])] for a list."""
    links = store.link_texts(objs)
    rows = []
    values = {}
    for v in store.value_model.objects.filter(**{f'{store.subject}__in': objs}):
        values.setdefault(getattr(v, f'{store.subject}_id'), {})[v.attribute_id] = v.value
    for obj in objs:
        mine = {**values.get(obj.pk, {}), **links.get(obj.pk, {})}
        rows.append((obj, [a.show(mine.get(a.pk, '')) for a in attributes]))
    return rows


def filters(attributes, query):
    return [(a, query.get(f'a{a.pk}', ''), query.get(f'a{a.pk}_min', ''), query.get(f'a{a.pk}_max', ''))
            for a in attributes if not a.is_link]



def shown(obj, node):
    """[(attribute, value)] of a part or asset for its page: a link attribute's value is what it links to."""
    store = store_for(obj)
    values = store.values(obj)
    return [(a, store.linked(a, obj) if a.is_link else a.show(values.get(a.pk, ''))) for a in (node.all_attributes() if node else [])]
