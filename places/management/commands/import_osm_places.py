import logging
from typing import List, Tuple

from django.core.management.base import BaseCommand
from places.services.osm_import import (
    POLAND_BBOX,
    import_osm_places,
)


class Command(BaseCommand):
    help = "Importuje eko-miejsca z OpenStreetMap (Overpass API) do modelu EcoPlace."

    def add_arguments(self, parser):
        parser.add_argument("--bbox", nargs=4, type=float, metavar=("S", "W", "N", "E"), help="Opcjonalny bounding box")
        parser.add_argument("--city", type=str, help="Ustaw miasto dla rekordów, jeśli brak w tagach OSM")
        parser.add_argument("--limit", type=int, default=1000, help="Limit rekordów do wstawienia (domyślnie 1000)")
        parser.add_argument("--dry-run", action="store_true", help="Tylko podgląd (bez zapisu do bazy)")

    def handle(self, *args, **options):
        bbox = tuple(options.get("bbox") or POLAND_BBOX)
        default_city = options.get("city") or ""
        limit = int(options.get("limit") or 1000)
        dry_run = bool(options.get("dry_run"))

        self.stdout.write(self.style.HTTP_INFO("Zapytanie do Overpass API (z mirrorami)..."))
        log = logging.getLogger(__name__)
        summary = import_osm_places(
            bbox=bbox, default_city=default_city, limit=limit, dry_run=dry_run, logger=log
        )

        if summary.get("used_api"):
            self.stdout.write(self.style.SUCCESS(f"Użyto endpointu: {summary['used_api']}"))
        else:
            self.stdout.write(self.style.WARNING(f"Nie udało się połączyć z Overpass: {summary.get('error')}"))

        self.stdout.write(
            f"Pobrano: {summary['fetched']}, Przetworzono: {summary['processed']}, Bez nazwy: {summary['skipped_unnamed']}"
        )
        if dry_run and summary.get("sample"):
            for row in summary["sample"]:
                self.stdout.write(f"DRY: {row}")
        self.stdout.write(self.style.SUCCESS(f"Utworzono nowych: {summary['created']}"))
