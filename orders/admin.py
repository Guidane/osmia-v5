from django.contrib import admin

from .models import Order, OrderLine


class LineInline(admin.TabularInline):
    model = OrderLine
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['number', 'vendor', 'status', 'ordered_on', 'expected_on', 'received_on']
    list_filter = ['status', 'vendor']
    search_fields = ['number', 'vendor__name', 'vendor_reference']
    inlines = [LineInline]
