from django.contrib import admin

from .models import Harness, HarnessEnd, HarnessItem, HarnessVersion, Wire


class EndInline(admin.TabularInline):
    model = HarnessEnd
    extra = 0


class ItemInline(admin.TabularInline):
    model = HarnessItem
    extra = 0


@admin.register(Harness)
class HarnessAdmin(admin.ModelAdmin):
    list_display = ['number', 'name', 'project', 'status', 'version']
    list_filter = ['status', 'project']
    search_fields = ['number', 'name']
    inlines = [EndInline, ItemInline]


admin.site.register([Wire, HarnessVersion])
