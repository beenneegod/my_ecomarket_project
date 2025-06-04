# challenges/urls.py
from django.urls import path
from . import views

app_name = 'challenges'

urlpatterns = [
    path('', views.challenge_list_view, name='challenge_list'),
    path('challenge/<slug:slug>/', views.challenge_detail_view, name='challenge_detail'),
    path('challenge/join/<int:challenge_id>/', views.join_challenge_view, name='join_challenge'),
    # URL для отметки выполнения челленджа (если будет отдельная POST-логика без формы на странице деталей)
    # path('challenge/complete/<int:participation_id>/', views.mark_challenge_complete_view, name='mark_challenge_complete'),
    path('my-progress/', views.my_progress_view, name='my_progress'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
]