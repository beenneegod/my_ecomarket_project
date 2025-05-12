# payments/urls.py

from django.urls import path
from . import views # Импортируем views из текущего приложения

app_name = 'payments' # Задаем пространство имен для этого приложения

urlpatterns = [
    # URL для страницы инициации платежа
    path('checkout/', views.checkout_and_payment, name='checkout'),
    # URL для страницы успешного завершения платежа
    path('completed/', views.payment_completed, name='completed'),
    # URL для страницы отмененного платежа
    path('canceled/', views.payment_canceled, name='canceled'),
    path('webhook/', views.stripe_webhook, name='stripe_webhook'),
]