"""Background email tasks for payments app."""

import logging
from urllib.parse import urlparse
from background_task import background
from django.conf import settings
from django.template.loader import render_to_string
from django.db import transaction
from store.models import Order, UserSubscription
from common.mail import send_email

logger = logging.getLogger(__name__)


def _email_base_context() -> dict:
    """Common context for emails: support contacts and site name/url."""
    site_url = getattr(settings, "SITE_URL", None)
    site_name = None
    if site_url:
        try:
            netloc = urlparse(site_url).netloc
            site_name = netloc.split(":")[0] if netloc else None
        except Exception:  # noqa: BLE001
            site_name = None
    if not site_name:
        site_name = "EcoMarket"
    return {
        "support_email": getattr(settings, "SUPPORT_EMAIL", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None),
        "support_phone": getattr(settings, "SUPPORT_PHONE", ""),
        "support_address": getattr(settings, "SUPPORT_ADDRESS", ""),
        "site_name": site_name,
        "site_url": site_url,
    }


@background(schedule=5)
def send_order_confirmation_email_task(order_id: int) -> bool:
    """Send order confirmation email in background."""
    try:
        # Lock row to prevent double-send races if task enqueued twice
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id)
            if order.email_sent:
                logger.info("TASK: order #%s email already sent, skipping", order.id)
                return True
            if not order.email:
                logger.warning("TASK: cannot send email for Order #%s: customer email is empty", order.id)
                return False
        if not order.email:
            logger.warning("TASK: cannot send email for Order #%s: customer email is empty", order.id)
            return False

        subject = f"Potwierdzenie zamówienia #{order.id} - EcoMarket"
        recipient_email = order.email
        from_email = settings.DEFAULT_FROM_EMAIL

        profile_url = None
        orders_url = None
        try:
            base = settings.SITE_URL
            profile_url = f"{base}/store/profile/edit/"
            orders_url = f"{base}/store/orders/"
        except Exception:  # noqa: BLE001 - best-effort URL build
            profile_url = None
            orders_url = None

        context = {
            "order": order,
            "user": order.user,
            "profile_url": profile_url,
            "orders_url": orders_url,
            **_email_base_context(),
        }
        plain_message = render_to_string("emails/order_confirmation.txt", context)
        html_message = render_to_string("emails/order_confirmation.html", context)

        send_email(
            subject=subject,
            to=[recipient_email],
            text=plain_message,
            html=html_message,
            from_email=from_email,
            fail_silently=False,
        )
        # Mark as sent after successful send
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id)
            order.email_sent = True
            order.save(update_fields=["email_sent", "updated_at"]) if hasattr(order, "updated_at") else order.save(update_fields=["email_sent"])  # noqa: E701
        logger.info("Email confirmation for Order #%s sent", order.id)
        return True
    except Order.DoesNotExist:
        logger.error("TASK ERROR: Order with ID %s not found. Email not sent", order_id)
        return False
    except Exception as e:  # noqa: BLE001 - log and return False
        logger.exception("TASK ERROR: Failed to send order email for Order #%s: %s", order_id, e)
        return False


@background(schedule=10)
def send_subscription_confirmation_email_task(user_subscription_id: int) -> bool:
    """Send subscription confirmation email in background."""
    try:
        user_sub = UserSubscription.objects.select_related("user", "box_type").get(id=user_subscription_id)
        if not user_sub.user or not user_sub.user.email:
            logger.warning(
                "TASK: cannot send subscription email for UserSubscription #%s: user or email missing",
                user_sub.id,
            )
            return False

        subject = f"Potwierdzenie subskrypcji: {user_sub.box_type.name} - EcoMarket"
        recipient_email = user_sub.user.email
        from_email = settings.DEFAULT_FROM_EMAIL
        profile_url = None
        try:
            base = settings.SITE_URL
            profile_url = f"{base}/store/profile/edit/"
        except Exception:
            profile_url = None
        context = {"user_subscription": user_sub, "profile_url": profile_url, **_email_base_context()}
        plain_message = render_to_string("emails/subscription_confirmation.txt", context)
        html_message = render_to_string("emails/subscription_confirmation.html", context)

        send_email(
            subject=subject,
            to=[recipient_email],
            text=plain_message,
            html=html_message,
            from_email=from_email,
            fail_silently=False,
        )
        logger.info(
            "Subscription confirmation email sent for UserSubscription #%s to %s",
            user_sub.id,
            user_sub.user.email,
        )
        return True
    except UserSubscription.DoesNotExist:
        logger.error("TASK ERROR: UserSubscription with ID %s not found. Email not sent", user_subscription_id)
        return False
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "TASK ERROR: Failed to send subscription email for UserSubscription #%s: %s",
            user_subscription_id,
            e,
        )
        return False


@background(schedule=10)
def send_subscription_canceled_email_task(user_subscription_id: int) -> bool:
    """Send subscription canceled notice in background."""
    try:
        user_sub = UserSubscription.objects.select_related("user", "box_type").get(id=user_subscription_id)
        if not user_sub.user or not user_sub.user.email:
            logger.warning(
                "TASK: cannot send cancel notice for UserSubscription #%s: user or email missing",
                user_sub.id,
            )
            return False

        subject = f'Twoja subskrypcja "{user_sub.box_type.name}" została anulowana - EcoMarket'
        recipient_email = user_sub.user.email
        from_email = settings.DEFAULT_FROM_EMAIL
        profile_url = None
        try:
            base = settings.SITE_URL
            profile_url = f"{base}/store/profile/edit/"
        except Exception:
            profile_url = None
        context = {"user_subscription": user_sub, "profile_url": profile_url, **_email_base_context()}
        plain_message = render_to_string("emails/subscription_canceled_notice.txt", context)
        html_message = render_to_string("emails/subscription_canceled_notice.html", context)

        send_email(
            subject=subject,
            to=[recipient_email],
            text=plain_message,
            html=html_message,
            from_email=from_email,
            fail_silently=False,
        )
        logger.info(
            "Subscription cancel notice sent for UserSubscription #%s to %s",
            user_sub.id,
            user_sub.user.email,
        )
        return True
    except UserSubscription.DoesNotExist:
        logger.error(
            "TASK ERROR: UserSubscription (cancel notice) with ID %s not found. Email not sent",
            user_subscription_id,
        )
        return False
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "TASK ERROR: Failed to send cancel notice for UserSubscription #%s: %s",
            user_subscription_id,
            e,
        )
        return False


@background(schedule=10)
def send_payment_failed_email_task(user_subscription_id: int) -> bool:
    """Send subscription payment failed email in background."""
    try:
        user_sub = UserSubscription.objects.select_related("user", "box_type").get(id=user_subscription_id)
        if not user_sub.user or not user_sub.user.email:
            logger.warning(
                "TASK: cannot send payment failed email for UserSubscription #%s: user or email missing",
                user_sub.id,
            )
            return False

        subject = f'Problem z płatnością za subskrypcję "{user_sub.box_type.name}" - EcoMarket'
        from_email = settings.DEFAULT_FROM_EMAIL
        profile_url = None
        try:
            base = settings.SITE_URL
            profile_url = f"{base}/store/profile/edit/"
        except Exception:
            profile_url = None
        context = {"user_subscription": user_sub, "profile_url": profile_url, **_email_base_context()}
        plain_message = render_to_string("emails/subscription_payment_failed.txt", context)
        html_message = render_to_string("emails/subscription_payment_failed.html", context)

        send_email(
            subject=subject,
            to=[user_sub.user.email],
            text=plain_message,
            html=html_message,
            from_email=from_email,
            fail_silently=False,
        )
        logger.info(
            "Payment failed email sent for UserSubscription #%s to %s",
            user_sub.id,
            user_sub.user.email,
        )
        return True
    except UserSubscription.DoesNotExist:
        logger.error(
            "TASK ERROR: UserSubscription (payment failed) with ID %s not found. Email not sent",
            user_subscription_id,
        )
        return False
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "TASK ERROR: Failed to send payment failed email for UserSubscription #%s: %s",
            user_subscription_id,
            e,
        )
        return False