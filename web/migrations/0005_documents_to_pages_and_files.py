"""The documentation as it was (one text, one picture and files per thing) becomes what it is now: the text a page
"Documentation" of the thing, the picture the thing's preview, the files its files. Links in the text to the old files
point to the new ones. Notifications pointing to wire diagrams at /projects/ point to /wire-diagrams/ (where they are
now; /projects/ is the projects')."""
import os

from django.db import migrations


def forward(apps, schema_editor):
    Document = apps.get_model('web', 'Document')
    Attachment = apps.get_model('web', 'Attachment')
    Page = apps.get_model('web', 'Page')
    PageVersion = apps.get_model('web', 'PageVersion')
    Notification = apps.get_model('web', 'Notification')

    def size(field):
        try:
            return field.size
        except (OSError, ValueError):
            return 0

    for doc in Document.objects.all():
        moved = {}
        if doc.image:
            Attachment.objects.create(content_type_id=doc.content_type_id, object_id=doc.object_id, file=doc.image.name,
                                      name=os.path.basename(doc.image.name)[:255], size=size(doc.image), preview=True,
                                      uploaded_by_id=doc.updated_by_id)
        for f in doc.files.all():
            new = Attachment.objects.create(content_type_id=doc.content_type_id, object_id=doc.object_id, file=f.file.name,
                                            name=f.name, size=size(f.file), uploaded_by_id=f.uploaded_by_id)
            Attachment.objects.filter(pk=new.pk).update(uploaded_at=f.uploaded_at)
            moved[f.pk] = new.pk
        body = doc.body or ''
        for old, new in moved.items():
            body = body.replace(f'/docs/files/{old}/', f'/files/{new}/')
        if body.strip():
            page = Page.objects.create(title='Documentation', body=body, content_type_id=doc.content_type_id, object_id=doc.object_id,
                                       created_by_id=doc.updated_by_id, updated_by_id=doc.updated_by_id)
            PageVersion.objects.create(page=page, number=1, title=page.title, body=body, saved_by_id=doc.updated_by_id)
    for note in Notification.objects.filter(url__startswith='/projects/'):
        note.url = '/wire-diagrams/' + note.url[len('/projects/'):]
        note.save(update_fields=['url'])


class Migration(migrations.Migration):
    dependencies = [('web', '0004_attachments_pages')]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
