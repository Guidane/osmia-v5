"""Telling people something: a notification each, with where to go."""
from .models import Notification


def notify(users, message, url=''):
    Notification.objects.bulk_create(Notification(user=u, message=str(message)[:500], url=url) for u in users)
