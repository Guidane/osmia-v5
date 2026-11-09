from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'status', 'owner']
    list_filter = ['status']
    search_fields = ['name', 'code']
    filter_horizontal = ['devices', 'assets']
