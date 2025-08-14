from django.urls import path
from . import views

app_name = "places"

urlpatterns = [
    path("", views.places_map, name="map"),
    path("api/places/", views.places_api, name="places_api"),
    path("api/places/<int:pk>/", views.place_detail_api, name="place_detail_api"),
    path("places/<int:pk>/add-review/", views.add_review, name="add_review"),
    path("reviews/<int:pk>/vote/<str:value>/", views.vote_review, name="vote_review"),
    path("add/", views.add_place, name="add_place"),
]
