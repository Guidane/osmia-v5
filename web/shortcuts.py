"""What the pages of every part of Osmia share: showing what went wrong, and the page that makes or changes one thing
with a form."""
from django.contrib import messages
from django.shortcuts import redirect, render


def errors(request, exc):
    """Each message of a ValidationError, shown on the next page."""
    for message in exc.messages:
        messages.error(request, message)


def edit_page(request, form, noun, then=None, saved=None):
    """A page making or changing one thing with ``form`` ("New <noun>" or "Change <it>"). When what was sent is
    right, it is saved, ``saved(obj, new)`` runs, and the page goes to it (or to ``then``)."""
    item = form.instance if form.instance.pk else None
    title, back = (f'Change {item}', item.get_absolute_url()) if item else (f'New {noun}', None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        if saved:
            saved(obj, item is None)
        messages.success(request, f'{obj} is saved.')
        return redirect(then or obj)
    return render(request, 'web/form.html', {'form': form, 'title': title, 'back': back})
