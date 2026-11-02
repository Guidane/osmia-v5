from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    path('', views.order_list, name='list'),
    path('new/', views.order_new, name='new'),
    path('<int:pk>/', views.order, name='order'),
    path('<int:pk>/lines/', views.line_add, name='line_add'),
    path('<int:pk>/lines/<int:line>/', views.line_change, name='line_change'),
    path('<int:pk>/place/', views.place, name='place'),
    path('<int:pk>/receive/', views.receive, name='receive'),
    path('<int:pk>/cancel/', views.cancel, name='cancel'),
]
