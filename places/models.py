from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class EcoPlace(models.Model):
    CATEGORY_CHOICES = [
        ("park", "Park"),
        ("market", "Targ/Market"),
        ("garden", "Ogród"),
        ("recycle", "Punkt recyklingu"),
        ("other", "Inne"),
    ]
    name = models.CharField(max_length=200, verbose_name="Nazwa")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other", verbose_name="Kategoria")
    city = models.CharField(max_length=120, verbose_name="Miasto")
    address = models.CharField(max_length=255, blank=True, verbose_name="Adres")
    lat = models.DecimalField(max_digits=9, decimal_places=6, verbose_name="Szerokość (lat)")
    lng = models.DecimalField(max_digits=9, decimal_places=6, verbose_name="Długość (lng)")
    description = models.TextField(blank=True, verbose_name="Opis")
    is_active = models.BooleanField(default=True, verbose_name="Aktywny")
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eco_places",
        verbose_name="Dodane przez",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Eko-miejsce"
        verbose_name_plural = "Eko-miejsca"
        ordering = ["city", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"


class PlaceReview(models.Model):
    place = models.ForeignKey(EcoPlace, on_delete=models.CASCADE, related_name="reviews", verbose_name="Miejsce")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="place_reviews", verbose_name="Użytkownik")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="Ocena (1-5)")
    comment = models.TextField(blank=True, verbose_name="Komentarz")
    is_approved = models.BooleanField(default=False, verbose_name="Zatwierdzony")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Utworzono")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Zaktualizowano")

    class Meta:
        verbose_name = "Opinia o miejscu"
        verbose_name_plural = "Opinie o miejscach"
        unique_together = ("place", "user")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.place.name} - {self.user} ({self.rating})"


class PlaceReviewVote(models.Model):
    review = models.ForeignKey(PlaceReview, on_delete=models.CASCADE, related_name="votes", verbose_name="Opinia")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_votes", verbose_name="Użytkownik")
    helpful = models.BooleanField(default=True, verbose_name="Pomocny")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("review", "user")
        verbose_name = "Głos na opinię"
        verbose_name_plural = "Głosy na opinie"

    def __str__(self) -> str:
        return f"{self.review_id} / {self.user_id} -> {'helpful' if self.helpful else 'not helpful'}"
