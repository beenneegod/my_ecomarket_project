from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.room_list, name='room_list'),
    path('rooms/create/', views.room_create, name='room_create'),
    path('rooms/<int:pk>/', views.room_detail, name='room_detail'),
    path('api/rooms/<int:pk>/messages/', views.messages_api, name='messages_api'),
    path('api/rooms/<int:pk>/messages/send/', views.send_message, name='send_message'),
    path('api/messages/<int:msg_id>/delete/', views.delete_message, name='delete_message'),
    path('api/rooms/<int:pk>/invite/', views.send_invite, name='send_invite'),
    path('api/invites/<int:invite_id>/accept/', views.accept_invite, name='accept_invite'),
    path('api/invites/<int:invite_id>/decline/', views.decline_invite, name='decline_invite'),
]
