from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('accounts/', include('accounts.urls')),
    path('admin/', admin.site.urls),   # administrators: users, and bulk changes to anything
    path('', include('web.urls')),
    path('', include('inventory.urls')),
    path('orders/', include('orders.urls')),
    path('devices/', include('devices.urls')),
    path('harnesses/', include('harnesses.urls')),
    path('wire-diagrams/', include('projects.urls')),
    path('projects/', include('work.urls')),
    path('budgets/', include('budgets.urls')),
    path('assets/', include('assets.urls')),
]
