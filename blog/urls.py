from django.urls import path, re_path
from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.PostListView.as_view(), name='post_list'),
    path('api/create_post/', views.CreatePostAPIView.as_view(), name='api_create_post'),
    path('comments/<int:comment_id>/rate/', views.rate_comment, name='rate_comment'),
    re_path(r'^(?P<slug>[-\w\d]+)/$', views.PostDetailView.as_view(), name='post_detail'),
]
