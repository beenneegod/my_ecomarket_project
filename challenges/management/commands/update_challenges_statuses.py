from django.core.management.base import BaseCommand
from challenges.services.statuses import update_statuses


class Command(BaseCommand):
    help = "Aktualizuje statusy wyzwań i uczestników na podstawie dat (do crona)."

    def handle(self, *args, **options):
        summary = update_statuses()
        self.stdout.write(self.style.SUCCESS(
            (
                "OK: challenges "
                f"upcoming={summary['ch_upcoming']}, "
                f"active={summary['ch_active']}, "
                f"completed_period={summary['ch_completed_period']}, "
                f"archived={summary['ch_archived']}; "
                f"participants failed={summary['parts_failed']}"
            )
        ))
