import json
import logging
from typing import Any, Dict, Iterable, List, Tuple

import requests
import time
from django.core.management.base import BaseCommand, CommandError
from places.models import EcoPlace

logger = logging.getLogger(__name__)

# Note: Data source is OpenStreetMap (OSM) via Overpass API.
# License: ODbL 1.0 (Open Database License). You must provide attribution.
# We'll add a small attribution to the map template automatically.

OVERPASS_APIS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
USER_AGENT = {
    "User-Agent": "EcoMarket/1.0 (+contact: admin@example.com)",
}

# Map OSM tags to our categories
OSM_CATEGORY_MAP: List[Tuple[str, str]] = [
    ("leisure=park", "park"),
    ("shop=farm", "market"),  # farmer's markets / shops with local products
    ("amenity=marketplace", "market"),
    ("landuse=allotments", "garden"),  # community gardens
    ("amenity=recycling", "recycle"),
]

# Simple city bounding boxes for Poland (rough country bbox). Users can filter further by city later.
# Using country wide bbox to pull a reasonable set; can be scoped per city if needed.
POLAND_BBOX = (49.0, 14.0, 55.0, 24.5)  # south, west, north, east


def build_overpass_query(bbox: Tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    filters = []
    for tag, _ in OSM_CATEGORY_MAP:
        k, v = tag.split("=")
        filters.append(f'node["{k}"="{v}"]({s},{w},{n},{e});')
        filters.append(f'way["{k}"="{v}"]({s},{w},{n},{e});')
        filters.append(f'relation["{k}"="{v}"]({s},{w},{n},{e});')
    union = "\n  ".join(filters)
    query = f"""
    [out:json][timeout:60];
    (
      {union}
    );
    out center;
    """
    return query


def normalize_name(tags: Dict[str, Any]) -> str:
    return tags.get("name") or tags.get("official_name") or tags.get("alt_name") or "Bez nazwy"


def normalize_address(tags: Dict[str, Any]) -> str:
    parts = []
    if tags.get("addr:street"):
        parts.append(str(tags.get("addr:street")))
    if tags.get("addr:housenumber"):
        parts.append(str(tags.get("addr:housenumber")))
    city = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village")
    if city:
        parts.append(str(city))
    return ", ".join(parts)


def normalize_city(tags: Dict[str, Any]) -> str:
    return str(tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village") or "")


def map_category(tags: Dict[str, Any]) -> str:
    for tag, category in OSM_CATEGORY_MAP:
        k, v = tag.split("=")
        if tags.get(k) == v:
            return category
    return "other"


class Command(BaseCommand):
    help = "Importuje eko-miejsca z OpenStreetMap (Overpass API) do modelu EcoPlace."

    def add_arguments(self, parser):
        parser.add_argument("--bbox", nargs=4, type=float, metavar=("S", "W", "N", "E"), help="Opcjonalny bounding box")
        parser.add_argument("--city", type=str, help="Ustaw miasto dla rekordów, jeśli brak w tagach OSM")
        parser.add_argument("--limit", type=int, default=1000, help="Limit rekordów do wstawienia (domyślnie 1000)")
        parser.add_argument("--dry-run", action="store_true", help="Tylko pokaż co бы wstawiono")

    def handle(self, *args, **options):
        bbox = tuple(options.get("bbox") or POLAND_BBOX)
        default_city = options.get("city") or ""
        limit = options.get("limit")
        dry_run = options.get("dry_run")

        query = build_overpass_query(bbox)
        self.stdout.write(self.style.HTTP_INFO("Zapytanie do Overpass API (z mirrorami)..."))
        data = {"elements": []}
        last_err = None
        for api in OVERPASS_APIS:
            try:
                resp = requests.post(api, data={"data": query}, headers=USER_AGENT, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                # Jeśli odpowiedź uzyskana, kończymy próby (elements może być pustą listą)
                self.stdout.write(self.style.SUCCESS(f"Użyto endpointu: {api}"))
                break
            except requests.RequestException as e:
                last_err = e
                self.stdout.write(self.style.WARNING(f"Problem z {api}: {e}"))
                time.sleep(2)

        elements = data.get("elements", [])
        self.stdout.write(f"Pobrano elementów: {len(elements)}")

        created = 0
        for el in elements[:limit]:
            tags = el.get("tags", {})
            name = normalize_name(tags)
            address = normalize_address(tags)
            city = normalize_city(tags) or default_city
            cat = map_category(tags)

            lat = None
            lng = None
            if "lat" in el and "lon" in el:
                lat, lng = el["lat"], el["lon"]
            elif "center" in el:
                lat, lng = el["center"].get("lat"), el["center"].get("lon")

            if lat is None or lng is None:
                continue

            desc_parts = []
            if tags.get("website"):
                desc_parts.append(f"www: {tags['website']}")
            if tags.get("opening_hours"):
                desc_parts.append(f"godziny: {tags['opening_hours']}")
            description = "; ".join(desc_parts)

            # Skip unnamed places
            if not name or name.strip().lower() == "bez nazwy":
                if dry_run:
                    self.stdout.write(f"SKIP (bez nazwy): [{cat}] {city} ({lat},{lng})")
                continue

            if dry_run:
                self.stdout.write(f"DRY: {name} [{cat}] {city} ({lat},{lng})")
                continue

            EcoPlace.objects.get_or_create(
                name=name,
                city=city,
                lat=lat,
                lng=lng,
                defaults={
                    "category": cat,
                    "address": address,
                    "description": description,
                    "is_active": True,  # importowane jako aktywne
                },
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Dodano/znaleziono rekordów: {created}"))
