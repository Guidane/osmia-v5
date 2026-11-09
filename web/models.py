"""What the website keeps of its own: the notifications people get; and what other parts build on: trees
(categories, locations, budgets, departments) and saved versions of designs."""
from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=500)
    url = models.CharField(max_length=300, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.message


class Version(models.Model):
    """A saved version of a design (a device, a harness): ``data`` is everything about it then, as the design's
    ``snapshot()`` makes it; ``restore(data)`` puts it back."""
    number = models.PositiveIntegerField()
    note = models.CharField(max_length=300, blank=True)
    data = models.JSONField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-number']

    def __str__(self):
        return f'v{self.number}'


class TreeWalk:
    """Walking a tree of records with a ``parent`` of their own kind."""
    def chain(self):
        """From the top of its tree down to this one."""
        nodes, node, seen = [], self, set()
        while node is not None and node.pk not in seen:
            seen.add(node.pk)
            nodes.append(node)
            node = node.parent
        return list(reversed(nodes))

    def below(self):
        """The pks of this one and every one under it."""
        found, todo = set(), [self.pk]
        while todo:
            found.update(todo)
            todo = list(type(self).objects.filter(parent_id__in=todo).exclude(pk__in=found).values_list('pk', flat=True))
        return found


class Tree(TreeWalk, models.Model):
    """A record with a parent of its own kind: categories, locations."""
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return self.path

    @property
    def path(self):
        """"Main building / Store / Shelf 3"."""
        return ' / '.join(node.name for node in self.chain())


    @classmethod
    def ordered(cls, nodes=None):
        """Every node (or those of ``nodes``, whole trees), depth first, as (node, depth): for lists and dropdowns."""
        children = {}
        for node in cls.objects.all() if nodes is None else nodes:
            children.setdefault(node.parent_id, []).append(node)
        out = []

        def walk(parent, depth):
            for node in children.get(parent, []):
                out.append((node, depth))
                walk(node.pk, depth + 1)
        walk(None, 0)
        return out


IMAGES = ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp')


class Attachment(models.Model):
    """A file or picture with something (a part, an order, a project, a documentation page, …): a photo, a datasheet,
    a drawing. One of its pictures can be its preview, shown on its page and in lists."""
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    file = models.FileField(upload_to='files/%Y/%m/')
    name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    preview = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-preview', 'name']
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def __str__(self):
        return self.name

    @property
    def is_image(self):
        return self.name.lower().rsplit('.', 1)[-1] in IMAGES


class Page(models.Model):
    """A documentation page: a title and its text (the editor's HTML, cleaned: see ``web.markup``), under another page
    or on its own; it belongs to something (a project, a part, a device, …) or to the general documentation."""
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')
    content_type = models.ForeignKey('contenttypes.ContentType', null=True, blank=True, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'title']
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('web:page', args=[self.pk])

    @property
    def owner(self):
        """What the page belongs to (None: the general documentation)."""
        if self.content_type_id is None:
            return None
        return self.content_type.get_all_objects_for_this_type(pk=self.object_id).first()

    def ancestors(self):
        out, at = [], self.parent
        while at is not None:
            out.insert(0, at)
            at = at.parent
        return out

    def below(self):
        """Its pages under it, all the way down."""
        out, todo = [], list(self.children.all())
        while todo:
            page = todo.pop(0)
            out.append(page)
            todo.extend(page.children.all())
        return out


class PageVersion(models.Model):
    """A page as it was saved: its history."""
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='versions')
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    saved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-number']
        constraints = [models.UniqueConstraint(fields=['page', 'number'], name='unique_page_version')]


class LabelLayout(models.Model):
    """What labels of parts or assets show by default, and on which sheet (see ``web.labels``)."""
    kind = models.CharField(max_length=10, unique=True)   # "part" or "asset"
    data = models.JSONField(default=dict)

    def __str__(self):
        return f'Labels of {self.kind}s'


class DemoRecord(models.Model):
    """A row the demo data made (see ``web.demo``): taken away when the demo data is switched off."""
    model = models.CharField(max_length=100)   # "inventory.Part"
    object_id = models.PositiveBigIntegerField()
