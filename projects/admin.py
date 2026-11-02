from django.contrib import admin

from .models import Configuration, Placement, Project


class PlacementInline(admin.TabularInline):
    model = Placement
    extra = 0


@admin.register(Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'parent']
    list_filter = ['project']
    inlines = [PlacementInline]


admin.site.register(Project)
