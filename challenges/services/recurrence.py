from __future__ import annotations

from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.utils.text import slugify
from typing import Dict

from challenges.models import Challenge


def _next_period(start, end, recurrence: str):
    if recurrence == 'weekly':
        return start + timedelta(weeks=1), end + timedelta(weeks=1)
    if recurrence == 'monthly':
        # naive month add: add ~31 days then normalize to next month same day
        # safer approach: use year/month math
        def add_month(d):
            y, m = d.year, d.month
            if m == 12:
                y += 1
                m = 1
            else:
                m += 1
            # keep day if possible, else clamp
            from calendar import monthrange
            last = monthrange(y, m)[1]
            day = min(d.day, last)
            return d.replace(year=y, month=m, day=day)
        return add_month(start), add_month(end)
    return None, None


def generate_recurrent_challenges(now=None) -> Dict[str, int]:
    """
    For template challenges with recurrence_type != none, ensure there is an upcoming/active instance.
    - If last instance ended before 'now', create a new instance shifted by recurrence.
    - Copy core fields; link template_challenge.
    """
    if now is None:
        now = timezone.now()

    created = 0
    with transaction.atomic():
        templates = Challenge.objects.filter(is_template=True, is_active=True).exclude(recurrence_type='none')
        for tmpl in templates:
            recurrence = tmpl.recurrence_type
            max_future = max(1, getattr(tmpl, 'max_future_instances', 1))
            # count current active or upcoming instances
            future_count = tmpl.instances.filter(status__in=['upcoming', 'active']).count()
            if future_count >= max_future:
                continue
            # find latest instance
            last = tmpl.instances.order_by('-end_date').first()
            base_start, base_end = (last.start_date, last.end_date) if last else (tmpl.start_date, tmpl.end_date)
            if not base_start or not base_end:
                continue
            next_start, next_end = _next_period(base_start, base_end, recurrence)
            if not next_start or not next_end:
                continue
            # create only if there is no overlapping/upcoming instance
            exists = tmpl.instances.filter(start_date__lte=next_end, end_date__gte=next_start).exists()
            if exists:
                continue
            # create new instance
            new = Challenge(
                title=tmpl.title,
                short_description=tmpl.short_description,
                description=tmpl.description,
                points_for_completion=tmpl.points_for_completion,
                start_date=next_start,
                end_date=next_end,
                image=tmpl.image,
                badge_name_reward=tmpl.badge_name_reward,
                badge_icon_class_reward=tmpl.badge_icon_class_reward,
                status='upcoming' if next_start > now else 'active',
                is_template=False,
                is_active=tmpl.is_active,
                template_challenge=tmpl,
                recurrence_type='none',
            )
            # slug: base + date suffix
            base_slug = slugify(tmpl.title)
            suffix = f"-{next_start.strftime('%Y%m%d')}"
            new.slug = f"{base_slug}{suffix}"[:220]
            new.save()
            created += 1

    return {"created": created}
