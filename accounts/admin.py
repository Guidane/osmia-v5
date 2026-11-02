from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, User


@admin.register(User)
class OsmiaUserAdmin(UserAdmin):
    list_display = ['username', 'first_name', 'last_name', 'email', 'department', 'is_superuser', 'is_active']
    list_filter = ['is_superuser', 'is_active', 'department']
    fieldsets = UserAdmin.fieldsets + (('Osmia', {'fields': ('job_title', 'phone', 'department')}),)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'manager']
