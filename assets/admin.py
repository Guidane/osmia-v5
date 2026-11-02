from django.contrib import admin

from .models import Asset, AssetEvent


class EventInline(admin.TabularInline):
    model = AssetEvent
    extra = 0


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ['number', 'name', 'kind', 'category', 'status', 'holder', 'keeper', 'calibrated_on']
    list_filter = ['kind', 'status', 'category']
    search_fields = ['number', 'name', 'serial']
    inlines = [EventInline]

