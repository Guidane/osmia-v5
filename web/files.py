"""Files and pictures of anything (see ``web.things``): added (picked, or dropped on its Files card), shown, one picture
made its preview, deleted. The first picture added to something becomes its preview."""
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Attachment
from .things import files_of, kind_of, owner_of, thing

INLINE = ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'pdf', 'txt')   # shown in the browser; the rest are downloaded


def card(request, obj):
    """The Files card of ``obj``, as HTML."""
    return render_to_string('web/_files.html', {'thing': obj, 'kind': kind_of(obj), 'files': files_of(obj)}, request=request)


def _answer(request, obj):
    if request.headers.get('X-Files-Card'):
        return HttpResponse(card(request, obj))
    return redirect(request.POST.get('next') or obj.get_absolute_url())


@login_required
@require_POST
def upload(request, kind, pk):
    obj = thing(kind, pk)
    ct = ContentType.objects.get_for_model(obj)
    previewed = kind == 'page' or files_of(obj).filter(preview=True).exists()
    added = []
    for upload in request.FILES.getlist('file'):
        item = Attachment(content_type=ct, object_id=obj.pk, file=upload, name=upload.name[:255], size=upload.size,
                          uploaded_by=request.user)
        if not previewed and item.is_image:
            item.preview = previewed = True
        item.save()
        added.append(item)
    if request.headers.get('X-Requested-With') == 'fetch':   # from the page editor: put in the text
        return JsonResponse({'files': [{'url': reverse('web:file', args=[f.pk]), 'name': f.name, 'image': f.is_image} for f in added]})
    return _answer(request, obj)


@login_required
def file(request, pk):
    item = get_object_or_404(Attachment, pk=pk)
    shown = item.name.lower().rsplit('.', 1)[-1] in INLINE
    response = FileResponse(item.file.open('rb'), filename=item.name, as_attachment=not shown)
    response['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_POST
def remove(request, pk):
    item = get_object_or_404(Attachment, pk=pk)
    obj = owner_of(item.content_type_id, item.object_id)
    item.file.delete(save=False)
    item.delete()
    return _answer(request, obj)


@login_required
@require_POST
def make_preview(request, pk):
    """This picture is what its thing looks like (again: none is)."""
    item = get_object_or_404(Attachment, pk=pk)
    others = Attachment.objects.filter(content_type_id=item.content_type_id, object_id=item.object_id)
    was = item.preview
    others.update(preview=False)
    if not was and item.is_image:
        Attachment.objects.filter(pk=item.pk).update(preview=True)
    return _answer(request, owner_of(item.content_type_id, item.object_id))


def delete_files_of(obj):
    """Its files gone, from the disk too (when it is deleted)."""
    for item in files_of(obj):
        item.file.delete(save=False)
        item.delete()
