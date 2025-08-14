from django.contrib import admin
from .models import EcoPlace, PlaceReview, PlaceReviewVote


@admin.register(EcoPlace)
class EcoPlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "city", "is_active")
    list_filter = ("category", "city", "is_active")
    search_fields = ("name", "city", "address")


@admin.register(PlaceReview)
class PlaceReviewAdmin(admin.ModelAdmin):
    list_display = ("place", "user", "rating", "is_approved", "created_at")
    list_filter = ("rating", "is_approved", "created_at")
    search_fields = ("place__name", "user__username", "comment")
    actions = [
        "mark_approved",
        "mark_unapproved",
    ]

    def mark_approved(self, request, queryset):
        queryset.update(is_approved=True)
    mark_approved.short_description = "Zatwierdź zaznaczone opinie"

    def mark_unapproved(self, request, queryset):
        queryset.update(is_approved=False)
    mark_unapproved.short_description = "Odrzuć zaznaczone opinie"


@admin.register(PlaceReviewVote)
class PlaceReviewVoteAdmin(admin.ModelAdmin):
    list_display = ("review", "user", "helpful", "created_at")
    list_filter = ("helpful", "created_at")
