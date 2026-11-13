from django.urls import path

from . import views

app_name = 'assets'

urlpatterns = [
    path('', views.asset_list, name='list'),
    path('new/', views.asset_form, name='new'),
    path('fields/', views.fields, name='fields'),
    path('fields/<int:pk>/', views.fields, name='field_edit'),
    path('fields/<int:pk>/delete/', views.field_delete, name='field_delete'),
    path('fields/<int:pk>/move/', views.field_move, name='field_move'),
    path('<int:pk>/', views.asset, name='asset'),
    path('<int:pk>/edit/', views.asset_form, name='edit'),
    path('<int:pk>/brief/', views.asset_brief, name='brief'),
    path('<int:pk>/act/', views.act, name='act'),
    path('<int:pk>/checklist/', views.checklist, name='checklist'),
]
