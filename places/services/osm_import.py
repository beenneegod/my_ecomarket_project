import logging
import time
from typing import Any, Dict, List, Tuple

import requests
from django.conf import settings

# Note: Data source is OpenStreetMap (OSM) via Overpass API.
# License: ODbL 1.0 (Open Database License). You must provide attribution.

OVERPASS_APIS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

OSM_CONTACT_EMAIL = getattr(settings, "OSM_CONTACT_EMAIL", "admin@example.com")
USER_AGENT = {
    "User-Agent": f"EcoMarket/1.0 (+contact: {OSM_CONTACT_EMAIL})",
}

# Map OSM tags to our categories
OSM_CATEGORY_MAP: List[Tuple[str, str]] = [
    ("leisure=park", "park"),
    ("shop=farm", "market"),  # farmer's markets / local product shops
    ("amenity=marketplace", "market"),
    ("landuse=allotments", "garden"),  # community gardens
    ("amenity=recycling", "recycle"),
]

# Poland bbox: south, west, north, east
POLAND_BBOX: Tuple[float, float, float, float] = (49.0, 14.0, 55.0, 24.5)

# Common city presets (bbox): S, W, N, E
CITY_PRESETS: Dict[str, Tuple[float, float, float, float]] = {
    # Canonical (with diacritics)
    "Warszawa": (52.05, 20.80, 52.35, 21.20),
    "Kraków": (49.97, 19.77, 50.12, 20.12),
    "Poznań": (52.33, 16.75, 52.50, 17.10),
    "Lublin": (51.18, 22.45, 51.32, 22.71),
    "Wrocław": (51.03, 16.83, 51.20, 17.18),
    "Gdańsk": (54.28, 18.50, 54.44, 18.75),
    # Aliases without diacritics for convenience
    "Krakow": (49.97, 19.77, 50.12, 20.12),
    "Poznan": (52.33, 16.75, 52.50, 17.10),
}


def build_overpass_query(bbox: Tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    filters: List[str] = []
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
    parts: List[str] = []
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


def import_osm_places(
    *,
    bbox: Tuple[float, float, float, float] | None = None,
    default_city: str = "",
    limit: int = 1000,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
):
    """
    Fetch eco-places from OSM Overpass and optionally insert into DB.

    Returns a dict with summary fields:
      used_api, fetched, processed, created, skipped_unnamed, sample (list)
    """
    from places.models import EcoPlace  # local import to avoid circulars at import time

    log = logger or logging.getLogger(__name__)
    bbox = tuple(bbox or POLAND_BBOX)  # type: ignore[assignment]

    query = build_overpass_query(bbox)  # build once

    data: Dict[str, Any] = {"elements": []}
    used_api = None
    last_err: Exception | None = None
    for api in OVERPASS_APIS:
        try:
            resp = requests.post(api, data={"data": query}, headers=USER_AGENT, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            used_api = api
            break
        except requests.RequestException as e:
            last_err = e
            log.warning("Problem z %s: %s", api, e)
            time.sleep(2)

    elements: List[Dict[str, Any]] = data.get("elements", [])  # type: ignore[assignment]
    fetched = len(elements)

    created = 0
    processed = 0
    skipped_unnamed = 0
    sample: List[str] = []

    for el in elements[: limit if limit and limit > 0 else None]:
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

        processed += 1

        # Skip unnamed
        if not name or name.strip().lower() == "bez nazwy":
            skipped_unnamed += 1
            continue

        desc_parts: List[str] = []
        if tags.get("website"):
            desc_parts.append(f"www: {tags['website']}")
        if tags.get("opening_hours"):
            desc_parts.append(f"godziny: {tags['opening_hours']}")
        description = "; ".join(desc_parts)

        if dry_run:
            if len(sample) < 20:  # return a small preview for UI
                sample.append(f"{name} [{cat}] {city} ({lat},{lng})")
            continue

        _, was_created = EcoPlace.objects.get_or_create(
            name=name,
            city=city,
            lat=lat,
            lng=lng,
            defaults={
                "category": cat,
                "address": address,
                "description": description,
                "is_active": True,
            },
        )
        if was_created:
            created += 1

    return {
        "used_api": used_api,
        "fetched": fetched,
        "processed": processed,
        "created": created,
        "skipped_unnamed": skipped_unnamed,
        "sample": sample,
        "error": None if used_api else (str(last_err) if last_err else "No Overpass endpoint responded"),
    }
