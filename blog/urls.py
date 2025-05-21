from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.PostListView.as_view(), name='post_list'),
    path('<slug:slug>/', views.PostDetailView.as_view(), name='post_detail'),
    # The PostDetailView handles comment submission via its post method,
    # so a separate URL for comment creation is not needed with the current view design.
]
