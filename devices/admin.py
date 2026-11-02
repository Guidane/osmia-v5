from django.contrib import admin

from .models import Connector, Device, DeviceVersion, Pin


class PinInline(admin.TabularInline):
    model = Pin
    extra = 0


@admin.register(Connector)
class ConnectorAdmin(admin.ModelAdmin):
    list_display = ['device', 'designator', 'name', 'part']
    inlines = [PinInline]


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['number', 'name', 'manufacturer', 'version']
    search_fields = ['number', 'name']


admin.site.register(DeviceVersion)
