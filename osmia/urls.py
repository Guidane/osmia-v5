from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

urlpatterns = [
    path('accounts/', include('accounts.urls')),
    path('admin/', admin.site.urls),   # administrators: users, and bulk changes to anything
    path('', include('web.urls')),
    path('', include('inventory.urls')),
    path('orders/', include('orders.urls')),
    path('devices/', include('devices.urls')),
    path('harnesses/', include('harnesses.urls')),
    path('wire-diagrams/', include('projects.urls')),
    re_path(r'^projects/(?P<rest>.*)$', RedirectView.as_view(url='/wire-diagrams/%(rest)s', query_string=True)),   # old links
    path('budgets/', include('budgets.urls')),
    path('assets/', include('assets.urls')),
]
