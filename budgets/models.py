"""Budgets: a tree (FY2026 › Engineering › Test equipment), each with an amount, an owner and maybe a project. What
is spent on one is the value of the orders charged to it (once placed) and its other costs, with all of that of the
budgets under it. See ``budgets.money``."""
from django.conf import settings
from django.db import models
from django.urls import reverse

from web.models import Tree


class Budget(Tree):
    number = models.CharField(max_length=50, blank=True)
    project = models.ForeignKey('projects.Project', null=True, blank=True, on_delete=models.SET_NULL, related_name='budgets')
    department = models.ForeignKey('accounts.Department', null=True, blank=True, on_delete=models.SET_NULL, related_name='budgets')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='budgets')
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta(Tree.Meta):
        ordering = ['number', 'name']

    def __str__(self):
        return f'{self.number} {self.name}'.strip()

    def get_absolute_url(self):
        return reverse('budgets:budget', args=[self.pk])


class Cost(models.Model):
    """Something spent on a budget that isn't an order: a service, travel, a course."""
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='costs')
    spent_on = models.DateField()
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-spent_on', '-pk']

    def __str__(self):
        return self.description
