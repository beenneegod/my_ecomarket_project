from __future__ import annotations

from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from typing import Dict

from challenges.models import Challenge, UserChallengeParticipation


def update_statuses(now=None) -> Dict[str, int]:
    """
    Update Challenge.status by dates and finalize participant outcomes for ended challenges.

    - before start_date => upcoming
    - between start and end => active
    - after end_date => completed_period (challenge); participants in joined/in_progress => failed

    Returns counters of updates applied.
    """
    if now is None:
        now = timezone.now()

    counters = {
        "ch_upcoming": 0,
        "ch_active": 0,
        "ch_completed_period": 0,
        "ch_archived": 0,
        "parts_failed": 0,
    }

    with transaction.atomic():
        # Upcoming
        upcoming_qs = Challenge.objects.filter(is_active=True, start_date__gt=now).exclude(status="upcoming")
        counters["ch_upcoming"] = upcoming_qs.update(status="upcoming")

        # Active
        active_qs = Challenge.objects.filter(
            is_active=True, start_date__lte=now, end_date__gte=now
        ).exclude(status="active")
        counters["ch_active"] = active_qs.update(status="active")

        # Completed (period ended)
        ended_qs = Challenge.objects.filter(is_active=True, end_date__lt=now).exclude(status__in=["completed_period", "archived"])
        counters["ch_completed_period"] = ended_qs.update(status="completed_period")

        # Mark participants of ended challenges who haven't completed as failed
        parts_qs = UserChallengeParticipation.objects.filter(
            challenge__end_date__lt=now,
            status__in=["joined", "in_progress"],
        )
        counters["parts_failed"] = parts_qs.update(status="failed")

    # Auto-archive challenges after a retention window
    days = getattr(settings, 'CHALLENGES_ARCHIVE_AFTER_DAYS', 60)
    archive_before = now - timedelta(days=days)
    archive_qs = Challenge.objects.filter(status="completed_period", end_date__lt=archive_before)
    counters["ch_archived"] = archive_qs.update(status="archived")

    return counters
