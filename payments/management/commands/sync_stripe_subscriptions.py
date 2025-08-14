import logging
from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import stripe

from store.models import UserSubscription

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Reconcile local UserSubscription records with Stripe by subscription ID. "
        "Usage: manage.py sync_stripe_subscriptions [--only-active] [--dry-run]"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-active",
            action="store_true",
            help="Process only subscriptions that are not already canceled locally.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not persist changes, only log what would change.",
        )

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        only_active = options.get("only_active", False)
        dry = options.get("dry_run", False)

        qs = UserSubscription.objects.exclude(stripe_subscription_id__isnull=True).exclude(
            stripe_subscription_id=""
        )
        if only_active:
            qs = qs.exclude(status="canceled")

        total = qs.count()
        self.stdout.write(self.style.NOTICE(f"Syncing {total} subscriptions from Stripe..."))
        updated = 0
        errors = 0

        for sub in qs.iterator():
            sid = sub.stripe_subscription_id
            try:
                s = stripe.Subscription.retrieve(sid)
                new_status = s.get("status")
                cps = s.get("current_period_start")
                cpe = s.get("current_period_end")
                cancel_at_period_end = s.get("cancel_at_period_end", False)

                mapped_status = sub.status
                if new_status == "active":
                    mapped_status = "active"
                elif new_status == "past_due":
                    mapped_status = "past_due"
                elif new_status == "canceled":
                    mapped_status = "canceled"
                elif new_status == "unpaid":
                    mapped_status = "past_due"
                elif new_status == "trialing":
                    mapped_status = "trialing"
                elif new_status in ["incomplete", "incomplete_expired"]:
                    mapped_status = new_status

                cps_dt = (
                    datetime.fromtimestamp(cps, tz=dt_timezone.utc) if cps is not None else None
                )
                cpe_dt = (
                    datetime.fromtimestamp(cpe, tz=dt_timezone.utc) if cpe is not None else None
                )

                changes = []
                if sub.status != mapped_status:
                    changes.append(f"status: {sub.status} -> {mapped_status}")
                if cps_dt and (not sub.current_period_start or sub.current_period_start != cps_dt):
                    changes.append("current_period_start: update")
                if cpe_dt and (not sub.current_period_end or sub.current_period_end != cpe_dt):
                    changes.append("current_period_end: update")
                if sub.cancel_at_period_end != cancel_at_period_end:
                    changes.append(
                        f"cancel_at_period_end: {sub.cancel_at_period_end} -> {cancel_at_period_end}"
                    )

                if not changes:
                    continue

                if dry:
                    logger.info("[DRY] Would update sub %s (%s): %s", sub.id, sid, ", ".join(changes))
                    continue

                sub.status = mapped_status
                if cps_dt:
                    sub.current_period_start = cps_dt
                if cpe_dt:
                    sub.current_period_end = cpe_dt
                sub.cancel_at_period_end = cancel_at_period_end
                sub.save(update_fields=[
                    "status",
                    "current_period_start",
                    "current_period_end",
                    "cancel_at_period_end",
                ])
                updated += 1
                logger.info("Updated sub %s (%s): %s", sub.id, sid, ", ".join(changes))
            except stripe.error.StripeError as e:
                errors += 1
                logger.error("Stripe error retrieving subscription %s: %s", sid, e)
            except Exception as e:
                errors += 1
                logger.exception("Unexpected error for subscription %s: %s", sid, e)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated: {updated}, Errors: {errors}, Total scanned: {total}."
            )
        )
