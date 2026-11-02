from django.urls import path

from . import views

app_name = 'projects'

urlpatterns = [
    path('', views.project_list, name='list'),
    path('new/', views.project_form, name='new'),
    path('<int:pk>/', views.project, name='project'),
    path('<int:pk>/edit/', views.project_form, name='edit'),
    path('<int:pk>/configurations/', views.configuration, name='configuration'),
    path('<int:pk>/change/', views.change, name='change'),
    path('<int:pk>/needs/', views.needs, name='needs'),
]
