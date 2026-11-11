"""Projects: what the work is for. A wire diagram or an order is of one project; a device or an asset (a tool too) can
be in several. A project can be part of another (a sub-project), as deep as need be."""
from django.conf import settings
from django.db import models
from django.urls import reverse

from web.models import TreeWalk


class Project(TreeWalk, models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ON_HOLD = 'on_hold', 'On hold'
        DONE = 'done', 'Done'

    code = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children', verbose_name='part of')
    status = models.CharField(max_length=10, choices=Status, default=Status.ACTIVE)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    department = models.ForeignKey('accounts.Department', null=True, blank=True, on_delete=models.SET_NULL, related_name='work_projects')
    devices = models.ManyToManyField('devices.Device', blank=True, related_name='work_projects')
    assets = models.ManyToManyField('assets.Asset', blank=True, related_name='work_projects')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.code} {self.name}'.strip()

    def get_absolute_url(self):
        return reverse('work:project', args=[self.pk])
