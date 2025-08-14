import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from store.models import UserSubscription

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Send subscription confirmation email immediately (bypassing background queue).\n"
        "Usage: manage.py send_subscription_confirmation_now --id <usersub_id>"
    )

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, help="UserSubscription ID")

    def handle(self, *args, **options):
        sub_id = options.get("id")
        if not sub_id:
            raise CommandError("--id is required")
        try:
            user_sub = UserSubscription.objects.select_related("user", "box_type").get(id=sub_id)
        except UserSubscription.DoesNotExist:
            raise CommandError(f"UserSubscription #{sub_id} not found")

        if not user_sub.user or not user_sub.user.email:
            raise CommandError(
                f"UserSubscription #{sub_id} has no user or user has no email"
            )

        subject = f"Potwierdzenie subskrypcji: {user_sub.box_type.name} - EcoMarket"
        recipient_email = user_sub.user.email
        from_email = settings.DEFAULT_FROM_EMAIL
        base = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
        profile_url = f"{base}/store/profile/edit/"
        context = {"user_subscription": user_sub, "profile_url": profile_url}

        plain_message = render_to_string("emails/subscription_confirmation.txt", context)
        html_message = render_to_string("emails/subscription_confirmation.html", context)

        send_mail(
            subject,
            plain_message,
            from_email,
            [recipient_email],
            html_message=html_message,
            fail_silently=False,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Subscription confirmation email sent to {recipient_email} for UserSubscription #{sub_id}"
        ))
