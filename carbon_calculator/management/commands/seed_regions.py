from django.core.management.base import BaseCommand
from carbon_calculator.models import Region, EmissionFactor, ActivityCategory
from django.db import transaction
from django.db.models import Q

DEFAULT_REGIONS = [
    {"code": "PL", "name": "Polska", "grid_intensity_kg_per_kwh": 0.724, "is_default": True},
]

ELECTRICITY_CATEGORY_SLUGS = [
    # Adjust if your electricity category uses another slug
    "dom-energia", "energia", "electricity"
]

class Command(BaseCommand):
    help = "Seed Region rows and flag electricity-related emission factors to use regional grid intensity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-flag-factors",
            action="store_true",
            help="Do not modify EmissionFactor.use_region_grid_intensity flags",
        )
        parser.add_argument(
            "--auto-detect-by-unit",
            action="store_true",
            help="Also flag factors where unit_name contains 'kWh'",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created_or_updated = 0
        # Seed regions
        for r in DEFAULT_REGIONS:
            obj, created = Region.objects.update_or_create(
                code=r["code"],
                defaults={
                    "name": r["name"],
                    "grid_intensity_kg_per_kwh": r["grid_intensity_kg_per_kwh"],
                    "is_default": r.get("is_default", False),
                }
            )
            created_or_updated += 1
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} region: {obj}"))

        # Ensure only one default region
        defaults = Region.objects.filter(is_default=True).order_by("id")
        if defaults.count() > 1:
            keep = defaults.first()
            Region.objects.exclude(id=keep.id).update(is_default=False)
            self.stdout.write(self.style.WARNING(f"Multiple defaults found; kept {keep}, unset others."))
        elif defaults.count() == 0:
            # Make PL default if exists
            pl = Region.objects.filter(code="PL").first()
            if pl:
                pl.is_default = True
                pl.save(update_fields=["is_default"])
                self.stdout.write(self.style.WARNING("No default region; set PL as default."))

        if options.get("no_flag_factors"):
            self.stdout.write("Skipped flagging emission factors.")
            return

        # Show available categories to help users adjust ELECTRICITY_CATEGORY_SLUGS
        existing_cats = list(ActivityCategory.objects.values_list("name", "slug"))
        if existing_cats:
            self.stdout.write("Available ActivityCategory slugs:")
            for name, slug in existing_cats:
                self.stdout.write(f" - {name} -> {slug}")

        # Flag electricity factors (by category slugs)
        cats = ActivityCategory.objects.filter(slug__in=ELECTRICITY_CATEGORY_SLUGS)
        factors_qs = EmissionFactor.objects.filter(activity_category__in=cats)
        updated = 0
        for f in factors_qs:
            if not f.use_region_grid_intensity:
                f.use_region_grid_intensity = True
                f.save(update_fields=["use_region_grid_intensity"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Flagged {updated} emission factors to use regional grid intensity by category slug match."))

        # Optionally, also flag by unit_name containing kWh
        if options.get("auto_detect_by_unit"):
            unit_qs = EmissionFactor.objects.filter(Q(unit_name__iexact="kwh") | Q(unit_name__icontains="kwh"))
            unit_updated = 0
            for f in unit_qs:
                if not f.use_region_grid_intensity:
                    f.use_region_grid_intensity = True
                    f.save(update_fields=["use_region_grid_intensity"])
                    unit_updated += 1
            self.stdout.write(self.style.SUCCESS(f"Additionally flagged {unit_updated} factors by unit_name containing 'kWh'."))

        self.stdout.write(self.style.SUCCESS("Seeding complete."))
