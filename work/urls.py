from django.urls import path

from . import views

app_name = 'work'

urlpatterns = [
    path('', views.project_list, name='list'),
    path('new/', views.project_form, name='new'),
    path('<int:pk>/', views.project, name='project'),
    path('<int:pk>/edit/', views.project_form, name='edit'),
    path('<int:pk>/link/', views.link, name='link'),
]
