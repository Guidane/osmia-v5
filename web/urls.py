from django.urls import path

from . import documents, labels, views

app_name = 'web'

urlpatterns = [
    path('', views.home, name='home'),
    path('docs/<slug:kind>/<int:pk>/', documents.document, name='document'),
    path('docs/<slug:kind>/<int:pk>/upload/', documents.upload, name='document_upload'),
    path('docs/<slug:kind>/<int:pk>/remove/', documents.remove, name='document_remove'),
    path('docs/<slug:kind>/<int:pk>/image/', documents.image, name='image'),
    path('docs/files/<int:pk>/', documents.file, name='document_file'),
    path('labels/<slug:kind>/', labels.sheet, name='labels'),
    path('demo/', views.demo_data, name='demo'),
    path('setup/', views.setup, name='setup'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/', views.notification_open, name='notification_open'),
]
