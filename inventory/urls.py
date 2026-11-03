from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('parts/', views.parts, name='parts'),
    path('parts/new/', views.part_form, name='part_new'),
    path('parts/find/', views.find, name='find'),
    path('parts/<int:pk>/', views.part, name='part'),
    path('parts/<int:pk>/edit/', views.part_form, name='part_edit'),
    path('parts/<int:pk>/stock/', views.part_stock, name='part_stock'),
    path('parts/<int:pk>/reorder/', views.part_reorder, name='part_reorder'),
    path('categories/', views.categories, name='categories'),
    path('categories/<int:pk>/', views.category, name='category'),
    path('categories/<int:pk>/attributes/', views.attribute_form, name='attribute_new'),
    path('categories/<int:pk>/attributes/<int:attribute>/', views.attribute_form, name='attribute_edit'),
    path('categories/<int:pk>/attributes/<int:attribute>/delete/', views.attribute_delete, name='attribute_delete'),
    path('categories/<int:pk>/attributes/<int:attribute>/move/', views.attribute_move, name='attribute_move'),
    path('locations/', views.locations, name='locations'),
    path('locations/new/', views.location_form, name='location_new'),
    path('locations/<int:pk>/', views.location, name='location'),
    path('locations/<int:pk>/edit/', views.location_form, name='location_edit'),
    path('vendors/', views.vendors, name='vendors'),
    path('vendors/new/', views.vendor_form, name='vendor_new'),
    path('vendors/<int:pk>/', views.vendor, name='vendor'),
    path('vendors/<int:pk>/edit/', views.vendor_form, name='vendor_edit'),
]
