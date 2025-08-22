from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import redirect, render
from django import forms
from .services.osm_import import POLAND_BBOX, CITY_PRESETS, import_osm_places
from .models import EcoPlace, PlaceReview, PlaceReviewVote


@admin.register(EcoPlace)
class EcoPlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "city", "is_active")
    list_filter = ("category", "city", "is_active")
    search_fields = ("name", "city", "address")

    # Simple admin view to run OSM import
    class ImportForm(forms.Form):
        # Put requested cities first
        def preset_choices():
            preferred = ["Kraków", "Krakow", "Poznań", "Poznan", "Warszawa", "Lublin"]
            seen = set()
            ordered = []
            for name in preferred:
                if name in CITY_PRESETS and name not in seen:
                    ordered.append((name, name))
                    seen.add(name)
            for name in CITY_PRESETS.keys():
                if name not in seen:
                    ordered.append((name, name))
                    seen.add(name)
            return [("", "— brak —")] + ordered

        preset = forms.ChoiceField(label="Preset miasta", required=False, choices=preset_choices())
        s = forms.FloatField(label="S (south)", initial=POLAND_BBOX[0])
        w = forms.FloatField(label="W (west)", initial=POLAND_BBOX[1])
        n = forms.FloatField(label="N (north)", initial=POLAND_BBOX[2])
        e = forms.FloatField(label="E (east)", initial=POLAND_BBOX[3])
        city = forms.CharField(label="Miasto (opcjonalnie)", required=False)
        limit = forms.IntegerField(label="Limit", initial=500, min_value=1, max_value=5000)
        dry_run = forms.BooleanField(label="Tylko podgląd (bez zapisu)", required=False, initial=True)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("import-osm/", self.admin_site.admin_view(self.import_osm_view), name="places_ecoplace_import_osm"),
        ]
        return custom + urls

    def import_osm_view(self, request):
        if request.method == "POST":
            form = self.ImportForm(request.POST)
            if form.is_valid():
                preset = form.cleaned_data.get("preset") or ""
                if preset and preset in CITY_PRESETS:
                    s, w, n, e = CITY_PRESETS[preset]
                    city = preset
                else:
                    s = form.cleaned_data["s"]
                    w = form.cleaned_data["w"]
                    n = form.cleaned_data["n"]
                    e = form.cleaned_data["e"]
                    city = form.cleaned_data["city"]
                limit = form.cleaned_data["limit"]
                dry = form.cleaned_data["dry_run"]

                summary = import_osm_places(bbox=(s, w, n, e), default_city=city, limit=limit, dry_run=dry)
                if summary.get("used_api"):
                    messages.success(request, f"Użyto endpointu: {summary['used_api']}")
                else:
                    messages.warning(request, f"Brak połączenia z Overpass: {summary.get('error')}")
                messages.info(
                    request,
                    f"Pobrano {summary['fetched']}, przetworzono {summary['processed']}, bez nazwy {summary['skipped_unnamed']}"
                )
                if dry and summary.get("sample"):
                    msgs = "\n".join(summary["sample"])
                    messages.info(request, f"Podgląd:\n{msgs}")
                messages.success(request, f"Utworzono nowych: {summary['created']}")
                return redirect("..")
        else:
            form = self.ImportForm()

        context = dict(
            self.admin_site.each_context(request),
            title="Import eko-miejsc z OSM (Overpass)",
            form=form,
        )
        return render(request, "admin/places/ecoplace/import_osm.html", context)


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
