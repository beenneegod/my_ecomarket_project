# carbon_calculator/urls.py
from django.urls import path
from . import views

app_name = 'carbon_calculator'

urlpatterns = [
    path('', views.calculate_footprint_view, name='calculate_page'), # Изменено имя для ясности
    path('history/', views.user_footprint_history_view, name='footprint_history'),
    path('methodology/', views.methodology_view, name='methodology_page'),
]