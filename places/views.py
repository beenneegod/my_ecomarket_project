from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from typing import Iterable, List, Optional
import math

from .models import EcoPlace, PlaceReview, PlaceReviewVote
from .forms import EcoPlaceForm, PlaceReviewForm
from django.db import models


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние между двумя координатами (км)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def places_map(request):
    cities = (
        EcoPlace.objects.filter(is_active=True)
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")
    )
    categories = EcoPlace.CATEGORY_CHOICES
    return render(
        request,
        "places/map.html",
        {"cities": cities, "categories": categories},
    )


@require_GET
def places_api(request):
    city = request.GET.get("city")
    categories: List[str] = request.GET.getlist("category")  # ?category=park&category=market
    center_lat = request.GET.get("center_lat")
    center_lng = request.GET.get("center_lng")
    radius_km = request.GET.get("radius_km")

    qs = EcoPlace.objects.filter(is_active=True)
    if city:
        qs = qs.filter(city__iexact=city)
    if categories:
        qs = qs.filter(category__in=categories)

    results = []
    # Фильтрация по радиусу (если заданы координаты центра)
    if center_lat and center_lng and radius_km:
        try:
            c_lat = float(center_lat)
            c_lng = float(center_lng)
            r = max(0.1, float(radius_km))
        except (TypeError, ValueError):
            c_lat = c_lng = None
            r = None
        if c_lat is not None and r is not None:
            for p in qs:
                d = _haversine_km(c_lat, c_lng, float(p.lat), float(p.lng))
                if d <= r:
                    results.append((p, d))
            # Сортируем по расстоянию
            results.sort(key=lambda t: t[1])
            data = [
                {
                    "id": p.id,
                    "name": p.name,
                    "category": p.category,
                    "city": p.city,
                    "address": p.address,
                    "lat": float(p.lat),
                    "lng": float(p.lng),
                    "description": p.description,
                    "distance_km": round(dist, 2),
                }
                for (p, dist) in results
            ]
            return JsonResponse({"results": data})

    # Без фильтра радиуса — просто отдаем список
    data = [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "city": p.city,
            "address": p.address,
            "lat": float(p.lat),
            "lng": float(p.lng),
            "description": p.description,
            "average_rating": round((p.reviews.filter(is_approved=True).aggregate(models.Avg("rating"))["rating__avg"] or 0), 2),
            "reviews_count": p.reviews.filter(is_approved=True).count(),
        }
        for p in qs
    ]
    return JsonResponse({"results": data})


@login_required
def add_place(request):
    if request.method == "POST":
        form = EcoPlaceForm(request.POST)
        if form.is_valid():
            place: EcoPlace = form.save(commit=False)
            place.added_by = request.user
            # Новые точки отправляются на модерацию: is_active=False
            place.is_active = False
            place.save()
            return redirect("places:map")
    else:
        form = EcoPlaceForm()
    return render(request, "places/add_place.html", {"form": form})


@require_GET
def place_detail_api(request, pk: int):
    place = get_object_or_404(EcoPlace, pk=pk, is_active=True)
    avg = place.reviews.filter(is_approved=True).aggregate(models.Avg("rating"))["rating__avg"] or 0
    reviews_qs = place.reviews.filter(is_approved=True).select_related("user").order_by("-created_at")
    # simple pagination via ?page=1&per=10
    try:
        page = max(1, int(request.GET.get("page", 1)))
        per = min(50, max(1, int(request.GET.get("per", 10))))
    except ValueError:
        page, per = 1, 10
    start, end = (page - 1) * per, page * per
    reviews_page = reviews_qs[start:end]

    reviews = [
        {
            "id": r.id,
            "user": r.user.username,
            "rating": r.rating,
            "comment": r.comment,
            "created_at": r.created_at.isoformat(),
            "helpful": r.votes.filter(helpful=True).count(),
            "not_helpful": r.votes.filter(helpful=False).count(),
        }
        for r in reviews_page
    ]
    return JsonResponse({
        "id": place.id,
        "name": place.name,
        "category": place.category,
        "city": place.city,
        "address": place.address,
        "lat": float(place.lat),
        "lng": float(place.lng),
        "description": place.description,
        "average_rating": round(avg, 2),
        "reviews_count": reviews_qs.count(),
        "page": page,
        "per": per,
        "reviews": reviews,
    })


@login_required
def add_review(request, pk: int):
    place = get_object_or_404(EcoPlace, pk=pk, is_active=True)
    if request.method == "POST":
        form = PlaceReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.place = place
            review.user = request.user
            try:
                review.save()
            except Exception:
                # Unique (place, user) => update instead
                existing = place.reviews.filter(user=request.user).first()
                if existing:
                    existing.rating = review.rating
                    existing.comment = review.comment
                    existing.save(update_fields=["rating", "comment", "updated_at"])
            return redirect("places:map")
    else:
        form = PlaceReviewForm()
    return render(request, "places/add_review.html", {"form": form, "place": place})


@login_required
def vote_review(request, pk: int, value: str):
    # value in {"up","down"}
    helpful = True if value == "up" else False
    review = get_object_or_404(PlaceReview, pk=pk, is_approved=True)
    obj, _created = PlaceReviewVote.objects.update_or_create(
        review=review, user=request.user, defaults={"helpful": helpful}
    )
    return redirect("places:map")
