def osmia(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    from .models import Notification
    return {'unread_notifications': Notification.objects.filter(user=user, read=False).count()}
