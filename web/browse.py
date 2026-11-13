"""Lists with a tree on the left (``web/_tree_nav.html``) and the details of the row picked on the right
(``web/_brief.html``, ``web/static/web/browser.js``): what the tree is made of."""


def node(label, url, count=None, on=False, depth=0, **more):
    return {'label': label, 'url': url, 'count': count, 'on': on, 'depth': depth, **more}


def nodes(tree, own, picked, href, label=str, depth=0, thumbs=False):
    """A tree's nodes for the left pane: ``tree`` [(node, depth)] (as ``ordered()`` gives it), ``own`` {pk: how many
    each holds itself} (each shown with those of the nodes under it), ``picked`` the one picked (its branch stands
    open), ``href(node)`` where picking one leads; ``thumbs``: each with its small picture."""
    children = {}
    for n, _ in tree:
        children.setdefault(n.parent_id, []).append(n.pk)

    def counted(pk):
        return own.get(pk, 0) + sum(counted(child) for child in children.get(pk, []))
    open_ = set(picked.chain_pks()) if picked is not None else set()
    return [node(label(n), href(n), counted(n.pk), picked is not None and picked.pk == n.pk, d + depth, open=n.pk in open_,
                 thumb=n if thumbs else None) for n, d in tree]


def keep(request, *names):
    """"&q=…&all=1": what of the address stays when another node of the tree is picked."""
    from urllib.parse import urlencode
    kept = {n: request.GET[n] for n in names if request.GET.get(n)}
    return ('&' + urlencode(kept)) if kept else ''
