# store/urls.py
from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('category/<slug:category_slug>/', views.product_list, name='product_list_by_category'),
    path('product/<slug:product_slug>/', views.product_detail, name='product_detail'),
    path('cart/', views.cart_detail, name='cart_detail'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'), # Оставляем ID для AJAX
    path('cart/remove/<int:product_id>/', views.cart_remove, name='cart_remove'), # Оставляем ID для AJAX
    path('cart/apply-coupon/', views.coupon_apply, name='coupon_apply'),
    path('cart/remove-coupon/', views.remove_coupon, name='remove_coupon'),
    path('orders/', views.order_history, name='order_history'),
    path('profile/edit/', views.profile_update, name='profile_update'),
    path('subscription-boxes/', views.subscription_box_list, name='subscription_box_list'),
    path('subscription-box/<slug:slug>/', views.subscription_box_detail, name='subscription_box_detail'),
    path('subscription/checkout/<int:box_type_id>/', views.process_subscription_checkout, name='process_subscription_checkout'),
    path('subscription/success/', views.subscription_success, name='subscription_success'),
    path('subscription/canceled/', views.subscription_canceled, name='subscription_canceled'),
    path('subscription/cancel/<int:subscription_id>/', views.cancel_subscription, name='cancel_subscription'),
    path('cart/count/', views.cart_count, name='cart_count'),
    path('product/<int:product_id>/rate/', views.rate_product, name='rate_product'),
    path('contact/', views.contact, name='contact'),
]