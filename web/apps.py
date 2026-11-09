from django.apps import AppConfig


class WebConfig(AppConfig):
    name = 'web'
    verbose_name = 'Osmia'

    def ready(self):
        """When something is deleted, its files (from the disk too) and its documentation pages go with it."""
        from django.apps import apps
        from django.contrib.contenttypes.models import ContentType
        from django.db.models.signals import post_delete

        from .things import KINDS

        def gone(sender, instance, **kwargs):
            from .models import Attachment, Page
            ct = ContentType.objects.get_for_model(sender)
            for item in Attachment.objects.filter(content_type=ct, object_id=instance.pk):
                item.file.delete(save=False)
                item.delete()
            if sender is not Page:
                Page.objects.filter(content_type=ct, object_id=instance.pk, parent=None).delete()

        for model, _ in KINDS.values():
            post_delete.connect(gone, sender=apps.get_model(model), weak=False, dispatch_uid=f'osmia-files-{model}')
