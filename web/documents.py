"""The documentation page of a part, asset, device, harness or project: its text, picture and files. Each kind is
named in its address as ``KINDS``: /docs/part/12/."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .markup import clean
from .models import Document, DocumentFile

KINDS = {'part': 'inventory.Part', 'asset': 'assets.Asset', 'device': 'devices.Device', 'harness': 'harnesses.Harness',
         'project': 'projects.Project'}


def kind_of(obj):
    return next(k for k, label in KINDS.items() if label.lower() == obj._meta.label_lower)


def document_of(obj, create=False):
    """``obj``'s document (made when ``create``, else None if there is none)."""
    ct = ContentType.objects.get_for_model(obj)
    if create:
        return Document.objects.get_or_create(content_type=ct, object_id=obj.pk)[0]
    return Document.objects.filter(content_type=ct, object_id=obj.pk).first()


def url_of(obj):
    return reverse('web:document', args=[kind_of(obj), obj.pk])


def _thing(kind, pk):
    from django.apps import apps
    if kind not in KINDS:
        raise Http404
    return get_object_or_404(apps.get_model(KINDS[kind]), pk=pk)


@login_required
def document(request, kind, pk):
    thing = _thing(kind, pk)
    doc = document_of(thing)
    editing = request.GET.get('edit') or request.method == 'POST'
    if request.method == 'POST':
        doc = document_of(thing, create=True)
        doc.body, doc.updated_by = clean(request.POST.get('body', '')), request.user
        doc.save()
        messages.success(request, 'The documentation is saved.')
        return redirect(request.path)
    return render(request, 'web/document.html', {'thing': thing, 'kind': kind, 'doc': doc, 'editing': editing,
                                                 'files': doc.files.all() if doc else []})


@login_required
@require_POST
def upload(request, kind, pk):
    """Files added to the documentation; ``image``: its picture (a new one replaces the old)."""
    thing = _thing(kind, pk)
    doc = document_of(thing, create=True)
    picture = request.FILES.get('image')
    if picture is not None:
        if not picture.content_type.startswith('image/'):
            messages.error(request, 'The picture has to be an image (PNG, JPEG, …).')
        else:
            if doc.image:
                doc.image.delete(save=False)
            doc.image = picture
            doc.updated_by = request.user
            doc.save()
    added = [DocumentFile.objects.create(document=doc, file=upload, name=upload.name[:255], uploaded_by=request.user)
             for upload in request.FILES.getlist('file')]
    if request.headers.get('X-Requested-With') == 'fetch':   # a picture put in the text from the editor
        return JsonResponse({'files': [{'url': reverse('web:document_file', args=[f.pk]), 'name': f.name, 'image': f.is_image} for f in added]})
    return redirect(url_of(thing))


@login_required
@require_POST
def remove(request, kind, pk):
    """Take the picture (``what`` = image) or a file (``what`` = its id) away."""
    thing = _thing(kind, pk)
    doc = document_of(thing)
    what = request.POST.get('what', '')
    if doc is not None and what == 'image' and doc.image:
        doc.image.delete(save=False)
        doc.image = ''
        doc.save()
    elif doc is not None and what.isdigit():
        item = doc.files.filter(pk=what).first()
        if item is not None:
            item.file.delete(save=False)
            item.delete()
    return redirect(url_of(thing))


@login_required
def file(request, pk):
    item = get_object_or_404(DocumentFile, pk=pk)
    return FileResponse(item.file.open('rb'), filename=item.name, as_attachment=not item.is_image)


@login_required
def image(request, kind, pk):
    doc = document_of(_thing(kind, pk))
    if doc is None or not doc.image:
        raise Http404
    return FileResponse(doc.image.open('rb'))
