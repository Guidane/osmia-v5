from django.urls import path

from . import files, labels, pages, views

app_name = 'web'

urlpatterns = [
    path('', views.home, name='home'),
    path('home/reports/', views.home_reports, name='home_reports'),
    path('files/<slug:kind>/<int:pk>/', files.upload, name='files'),
    path('files/<int:pk>/', files.file, name='file'),
    path('notes/<slug:kind>/<int:pk>/', views.notes, name='notes'),
    path('brief/<slug:kind>/<int:pk>/', views.brief, name='brief'),
    path('files/<int:pk>/remove/', files.remove, name='file_remove'),
    path('files/<int:pk>/preview/', files.make_preview, name='file_preview'),
    path('docs/', pages.docs, name='docs'),
    path('docs/new/', pages.page_new, name='page_new'),
    path('docs/<int:pk>/', pages.page, name='page'),
    path('docs/<int:pk>/edit/', pages.page_edit, name='page_edit'),
    path('docs/<int:pk>/delete/', pages.page_delete, name='page_delete'),
    path('docs/<int:pk>/history/', pages.history, name='page_history'),
    path('docs/<int:pk>/history/<int:number>/restore/', pages.restore, name='page_restore'),
    path('labels/<slug:kind>/', labels.sheet, name='labels'),
    path('demo/', views.demo_data, name='demo'),
    path('transfer/', views.transfer, name='transfer'),
    path('update/', views.update_osmia, name='update'),
    path('setup/', views.setup, name='setup'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/', views.notification_open, name='notification_open'),
]
