from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse

from web.models import Tree


class Department(Tree):
    """A part of the company (a tree: Engineering › Test), with its manager, its people, budgets and projects."""
    description = models.TextField(blank=True)
    manager = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='managed')

    class Meta(Tree.Meta):
        constraints = [models.UniqueConstraint(fields=['parent', 'name'], name='unique_department_name')]

    def get_absolute_url(self):
        return reverse('accounts:department', args=[self.pk])


class User(AbstractUser):
    """A person who logs in. Passwords are Django's own."""
    job_title = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name='members')
    home_reports = models.JSONField(null=True, blank=True, editable=False)   # the reports on their Home, in order (None: as it comes)

    class Meta:
        ordering = ['first_name', 'last_name', 'username']

    def __str__(self):
        return self.get_full_name() or self.username

    def get_absolute_url(self):
        return reverse('accounts:users')
