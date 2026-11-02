from django.urls import path

from . import views

app_name = 'budgets'

urlpatterns = [
    path('', views.budget_list, name='list'),
    path('new/', views.budget_form, name='new'),
    path('<int:pk>/', views.budget, name='budget'),
    path('<int:pk>/edit/', views.budget_form, name='edit'),
    path('<int:pk>/costs/', views.cost_add, name='cost_add'),
    path('<int:pk>/costs/<int:cost>/delete/', views.cost_delete, name='cost_delete'),
]
