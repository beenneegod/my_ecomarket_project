from django.core.management.base import BaseCommand
from django.utils import timezone

from challenges.services.statuses import update_statuses
from challenges.services.recurrence import generate_recurrent_challenges


class Command(BaseCommand):
    help = "Combined scheduler tick: updates challenge statuses (with auto-archive) and generates recurring instances."

    def handle(self, *args, **options):
        now = timezone.now()
        s1 = update_statuses(now=now)
        s2 = generate_recurrent_challenges(now=now)
        self.stdout.write(self.style.SUCCESS(
            (
                "cron_tick OK | "
                f"upcoming={s1['ch_upcoming']}, active={s1['ch_active']}, completed_period={s1['ch_completed_period']}, archived={s1['ch_archived']}; "
                f"participants_failed={s1['parts_failed']}; created_recurring={s2['created']}"
            )
        ))
