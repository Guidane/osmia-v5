"""Projects and their configurations. A project's configurations form a tree: each one is what its parent is, with
its own changes (``Placement`` rows): a device or harness added, taken away, swapped, moved on the diagram or
plugged in differently. A configuration without a parent is a setup of its own. See ``projects.configs``."""
from django.conf import settings
from django.db import models
from django.urls import reverse

from web.models import TreeWalk


class Project(models.Model):
    code = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    department = models.ForeignKey('accounts.Department', null=True, blank=True, on_delete=models.SET_NULL, related_name='projects')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.code} {self.name}'.strip()

    def get_absolute_url(self):
        return reverse('projects:project', args=[self.pk])


class Configuration(TreeWalk, models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='configurations')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('projects:project', args=[self.project_id]) + f'?config={self.pk}'



class Placement(models.Model):
    """One change a configuration makes: to the device or harness its ``key`` names (the same key all down the tree).
    A row replaces what the parent has for that key; ``removed`` takes it away."""
    class Kind(models.TextChoices):
        DEVICE = 'device', 'Device'
        HARNESS = 'harness', 'Harness'

    configuration = models.ForeignKey(Configuration, on_delete=models.CASCADE, related_name='placements')
    key = models.CharField(max_length=40)
    kind = models.CharField(max_length=10, choices=Kind)
    removed = models.BooleanField(default=False)
    device = models.ForeignKey('devices.Device', null=True, blank=True, on_delete=models.PROTECT, related_name='placements')
    label = models.CharField(max_length=100, blank=True)          # a device's name in the project, e.g. Load board 2
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    harness = models.ForeignKey('harnesses.Harness', null=True, blank=True, on_delete=models.CASCADE, related_name='placements')
    ends = models.JSONField(default=dict, blank=True)              # a harness's {end id: key of the device it plugs into}

    class Meta:
        ordering = ['pk']
        constraints = [models.UniqueConstraint(fields=['configuration', 'key'], name='unique_placement_key')]

    def __str__(self):
        return f'{self.configuration}: {self.key}'
