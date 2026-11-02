from django.urls import path

from . import views

app_name = 'devices'

urlpatterns = [
    path('', views.device_list, name='list'),
    path('new/', views.device_form, name='new'),
    path('<int:pk>/', views.device, name='device'),
    path('<int:pk>/edit/', views.device_form, name='edit'),
    path('<int:pk>/connectors/new/', views.connector_form, name='connector_new'),
    path('<int:pk>/connectors/<int:connector>/', views.connector_form, name='connector_edit'),
    path('<int:pk>/connectors/<int:connector>/delete/', views.connector_delete, name='connector_delete'),
    path('<int:pk>/connectors/<int:connector>/pins/', views.pins, name='pins'),
    path('<int:pk>/versions/', views.save_version, name='save_version'),
    path('<int:pk>/versions/<int:number>/', views.version, name='version'),
    path('<int:pk>/versions/<int:number>/restore/', views.restore, name='restore'),
]
