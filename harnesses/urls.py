from django.urls import path

from . import views

app_name = 'harnesses'

urlpatterns = [
    path('', views.harness_list, name='list'),
    path('new/', views.harness_form, name='new'),
    path('<int:pk>/', views.harness, name='harness'),
    path('<int:pk>/edit/', views.harness_form, name='edit'),
    path('<int:pk>/ends/', views.ends, name='ends'),
    path('<int:pk>/pinout/', views.pinout, name='pinout'),
    path('<int:pk>/items/', views.items, name='items'),
    path('<int:pk>/versions/', views.save_version, name='save_version'),
    path('<int:pk>/versions/<int:number>/', views.version, name='version'),
    path('<int:pk>/versions/<int:number>/restore/', views.restore, name='restore'),
    path('<int:pk>/units/', views.unit_add, name='unit_add'),
]
