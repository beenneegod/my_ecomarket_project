"""Payments views: checkout, success/cancel pages, and Stripe webhooks."""

from decimal import Decimal
import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render, reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

import stripe

from store.cart import Cart
from store.forms import OrderCreateForm
from store.models import (
    Coupon,
    Order,
    OrderItem,
    Product,
    Profile,
    SubscriptionBoxType,
    UserCoupon,
    UserSubscription,
)
from .tasks import (
    send_order_confirmation_email_task,
    send_payment_failed_email_task,
    send_subscription_canceled_email_task,
    send_subscription_confirmation_email_task,
)

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def checkout_and_payment(request):
    """
    Show address form (GET) and on submit (POST) validate and create a Stripe checkout session.
    Pre-create Order and OrderItems, attach order_id to Stripe session metadata.
    """
    cart = Cart(request)
    if len(cart) == 0:
        messages.error(request, "Ваша корзина пуста.")
        return redirect('store:product_list')

    if request.method == 'POST':
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            if request.user.is_authenticated:
                order.user = request.user
            order.save()
            for item in cart:
                OrderItem.objects.create(
                    order=order,
                    product=item['product_obj'],
                    price=item['price'],
                    quantity=item['quantity'],
                )

            # Apply coupon to order object (fields only); actual UserCoupon marking happens in webhook
            coupon_id = request.session.get('coupon_id')
            if coupon_id:
                try:
                    coupon = Coupon.objects.get(id=coupon_id)
                    order.coupon = coupon
                    order.discount = coupon.discount
                except Coupon.DoesNotExist:
                    order.coupon = None
                    order.discount = Decimal('0')
            else:
                order.coupon = None
                order.discount = Decimal('0')
            order.save()

            success_url = request.build_absolute_uri(reverse('payments:completed'))
            cancel_url = request.build_absolute_uri(reverse('payments:canceled'))

            session_data = {
                'mode': 'payment',
                'success_url': success_url,
                'cancel_url': cancel_url,
                'line_items': [],
                'customer_email': order.email,
                'metadata': {
                    'user_id': str(request.user.id) if request.user.is_authenticated else None,
                    'first_name': order.first_name,
                    'last_name': order.last_name,
                    'address_line_1': order.address_line_1,
                    'address_line_2': order.address_line_2,
                    'postal_code': order.postal_code,
                    'city': order.city,
                    'country': order.country,
                    'order_id': order.id,
                },
            }

            for item in cart:
                product_obj = item['product_obj']
                if cart.coupon:
                    price_decimal = Decimal(item['price']) * (
                        Decimal('1') - Decimal(cart.coupon.discount) / Decimal('100')
                    )
                else:
                    price_decimal = Decimal(item['price'])
                session_data['line_items'].append(
                    {
                        'price_data': {
                            'unit_amount': int(price_decimal * Decimal('100')),
                            'currency': 'pln',
                            'product_data': {
                                'name': product_obj.name,
                                'metadata': {'product_db_id': product_obj.id},
                            },
                        },
                        'quantity': item['quantity'],
                    }
                )

            session_data['metadata']['coupon_code'] = request.session.get(
                'coupon_code', ''
            )
            session_data['metadata']['coupon_discount'] = str(
                request.session.get('coupon_discount', 0)
            )

            try:
                total_pln = cart.get_total_price()
                if total_pln < Decimal('2.00'):
                    messages.error(
                        request,
                        f"Минимальная сумма заказа для оплаты составляет 2.00 PLN. Ваша текущая сумма: {total_pln} PLN.",
                    )
                    return render(request, 'payments/checkout.html', {'cart': cart, 'form': form})

                session = stripe.checkout.Session.create(**session_data)
                return redirect(session.url, code=303)
            except stripe.error.StripeError as e:
                logger.error("Stripe error creating checkout session: %s", e)
                messages.error(request, f"Ошибка платежной системы: {e}. Попробуйте снова.")
                return render(request, 'payments/checkout.html', {'cart': cart, 'form': form})
            except Exception as e:
                logger.exception("Unexpected error creating checkout session: %s", e)
                messages.error(
                    request, "Произошла непредвиденная ошибка при создании платежной сессии."
                )
                return render(request, 'payments/checkout.html', {'cart': cart, 'form': form})
        else:
            messages.error(request, "Пожалуйста, исправьте ошибки в форме адреса.")
    else:
        initial_data = {}
        if request.user.is_authenticated:
            initial_data = {
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
            }
        form = OrderCreateForm(initial=initial_data)

    return render(request, 'payments/checkout.html', {'cart': cart, 'form': form})


def payment_completed(request):
    """Success page; clear cart for fast UX (webhook finalizes order)."""
    cart = Cart(request)
    cart.clear()
    return render(request, 'payments/completed.html')


def payment_canceled(request):
    """Canceled page."""
    return render(request, 'payments/canceled.html')


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    if not endpoint_secret:
        logger.error("WEBHOOK: STRIPE_WEBHOOK_SECRET not configured")
        return HttpResponse(status=500, content="Webhook secret not configured.")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        logger.error("WEBHOOK: invalid payload: %s", e)
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error("WEBHOOK: invalid signature: %s", e)
        return HttpResponse(status=400)
    except Exception as e:
        logger.exception("WEBHOOK: error constructing event: %s", e)
        return HttpResponse(status=500)

    event_type = event.get('type')
    logger.info("WEBHOOK: constructed event id=%s type=%s", event.get('id'), event_type)

    if event_type == 'checkout.session.completed':
        session = event['data']['object']
        session_id = session.id
        session_mode = session.get('mode')
        session_payment_status = session.get('payment_status')
        logger.info(
            "WEBHOOK checkout.session.completed: session_id=%s mode=%s payment_status=%s",
            session_id,
            session_mode,
            session_payment_status,
        )

        if session_payment_status == 'paid':
            if session_mode == 'subscription':
                try:
                    stripe_subscription_id_from_session = session.get('subscription')
                    logger.info(
                        "WEBHOOK checkout.session.completed (subscription): stripe_subscription_id_from_session='%s'",
                        stripe_subscription_id_from_session,
                    )

                    if (
                        stripe_subscription_id_from_session
                        and UserSubscription.objects.filter(
                            stripe_subscription_id=stripe_subscription_id_from_session
                        ).exists()
                    ):
                        existing_sub = UserSubscription.objects.get(
                            stripe_subscription_id=stripe_subscription_id_from_session
                        )
                        logger.info(
                            "WEBHOOK: UserSubscription for Stripe sub '%s' (id %s) already exists. Skip.",
                            stripe_subscription_id_from_session,
                            existing_sub.id,
                        )
                        return HttpResponse(status=200)

                    metadata = session.get('metadata', {})
                    django_user_id = metadata.get('django_user_id')
                    box_type_id = metadata.get('subscription_box_type_id')
                    stripe_customer_id = session.get('customer')

                    if not all([
                        django_user_id,
                        box_type_id,
                        stripe_subscription_id_from_session,
                        stripe_customer_id,
                    ]):
                        logger.error(
                            "WEBHOOK: missing data for subscription session_id=%s", session_id
                        )
                        return HttpResponse(status=400)

                    User = get_user_model()
                    try:
                        user = User.objects.get(id=int(django_user_id))
                    except (User.DoesNotExist, ValueError, TypeError) as e:
                        logger.warning(
                            "WEBHOOK: user with id=%s not found for session %s: %s",
                            django_user_id,
                            session_id,
                            e,
                        )
                        return HttpResponse(status=400)

                    try:
                        box_type = SubscriptionBoxType.objects.get(id=int(box_type_id))
                    except (SubscriptionBoxType.DoesNotExist, ValueError, TypeError):
                        logger.error(
                            "WEBHOOK: box_type id=%s not found or invalid for session %s",
                            box_type_id,
                            session_id,
                        )
                        return HttpResponse(status=400)

                    with transaction.atomic():
                        profile, created = Profile.objects.get_or_create(user=user)
                        if not profile.stripe_customer_id:
                            profile.stripe_customer_id = stripe_customer_id
                            profile.save()

                        subscription, sub_created = UserSubscription.objects.update_or_create(
                            stripe_subscription_id=stripe_subscription_id_from_session,
                            defaults={
                                'user': user,
                                'box_type': box_type,
                                'stripe_customer_id': stripe_customer_id,
                                'status': 'incomplete',
                            },
                        )
                        logger.info(
                            "WEBHOOK: UserSubscription %s for Stripe sub '%s', id=%s, status=incomplete",
                            'CREATED' if sub_created else 'UPDATED',
                            stripe_subscription_id_from_session,
                            subscription.id,
                        )
                except Exception as e:
                    logger.exception(
                        "WEBHOOK: failed to process subscription session %s: %s",
                        session_id,
                        e,
                    )
                    return HttpResponse(status=500)

            elif session_mode == 'payment':
                try:
                    if Order.objects.filter(stripe_id=session_id, paid=True).exists():
                        logger.info(
                            "WEBHOOK: payment order for session %s already processed. Skip.",
                            session_id,
                        )
                        return HttpResponse(status=200)

                    metadata = session.get('metadata', {})
                    order_id_meta = metadata.get('order_id')
                    customer_details_email = session.get('customer_details', {}).get('email')

                    if not order_id_meta:
                        logger.error(
                            "WEBHOOK: payment session %s without order_id in metadata.",
                            session_id,
                        )
                        return HttpResponse(status=400)
                    # Lock and update the order inside a DB transaction.
                    with transaction.atomic():
                        try:
                            order = Order.objects.select_for_update().get(id=int(order_id_meta))
                        except (Order.DoesNotExist, ValueError, TypeError) as e:
                            logger.error(
                                "WEBHOOK: order_id=%s from metadata not found/invalid for session %s: %s",
                                order_id_meta,
                                session_id,
                                e,
                            )
                            return HttpResponse(status=400)

                        if order.paid and order.stripe_id == session_id:
                            logger.info(
                                "WEBHOOK: order %s already marked paid for session %s",
                                order.id,
                                session_id,
                            )
                            return HttpResponse(status=200)

                        order.paid = True
                        order.stripe_id = session_id
                        if customer_details_email and not order.email:
                            order.email = customer_details_email

                        applied_coupon_code = metadata.get('coupon_code')
                        if applied_coupon_code and order.user:
                            try:
                                coupon_obj = Coupon.objects.get(code=applied_coupon_code)
                                user_coupon = UserCoupon.objects.filter(
                                    user=order.user, coupon=coupon_obj, is_used=False
                                ).first()
                                if user_coupon:
                                    now = timezone.now()
                                    if (
                                        coupon_obj.active
                                        and coupon_obj.valid_from <= now
                                        and coupon_obj.valid_to >= now
                                    ):
                                        user_coupon.is_used = True
                                        user_coupon.used_at = now
                                        user_coupon.order = order
                                        user_coupon.save()
                                        logger.info(
                                            "WEBHOOK: marked UserCoupon %s as used for order %s",
                                            user_coupon.id,
                                            order.id,
                                        )
                            except Coupon.DoesNotExist:
                                logger.info(
                                    "WEBHOOK: coupon code %s from metadata not found for order %s",
                                    applied_coupon_code,
                                    order.id,
                                )

                        order.save()
                        # Schedule email only after the transaction commits successfully
                        transaction.on_commit(
                            lambda oid=order.id: send_order_confirmation_email_task(oid)
                        )

                    logger.info(
                        "WEBHOOK: order %s marked paid for session %s",
                        order.id,
                        session_id,
                    )
                    logger.info(
                        "WEBHOOK: queued order confirmation email for order %s",
                        order.id,
                    )
                except Exception as e:
                    logger.exception(
                        "WEBHOOK: failed to process payment session %s: %s",
                        session_id,
                        e,
                    )
                    return HttpResponse(status=500)
            else:
                logger.error(
                    "WEBHOOK: unknown session mode '%s' for session %s",
                    session_mode,
                    session_id,
                )
                return HttpResponse(status=400)

    elif event_type in ['customer.subscription.created', 'customer.subscription.updated']:
        subscription_stripe_obj = event['data']['object']
        stripe_subscription_id = subscription_stripe_obj.id
        new_stripe_status = subscription_stripe_obj.get('status')
        stripe_customer_id_from_sub = subscription_stripe_obj.get('customer')

        logger.info(
            "WEBHOOK %s: processing subscription_id=%s new_status=%s",
            event_type,
            stripe_subscription_id,
            new_stripe_status,
        )

        try:
            user_subscription = UserSubscription.objects.get(
                stripe_subscription_id=stripe_subscription_id
            )
            logger.info(
                "WEBHOOK %s: found UserSubscription id=%s old_status=%s",
                event_type,
                user_subscription.id,
                user_subscription.status,
            )

            original_local_status = user_subscription.status

            if new_stripe_status == 'active':
                user_subscription.status = 'active'
            elif new_stripe_status == 'past_due':
                user_subscription.status = 'past_due'
            elif new_stripe_status == 'canceled':
                user_subscription.status = 'canceled'
            elif new_stripe_status == 'unpaid':
                user_subscription.status = 'past_due'
            elif new_stripe_status == 'trialing':
                user_subscription.status = 'trialing'
            elif new_stripe_status in ['incomplete', 'incomplete_expired']:
                if new_stripe_status in [choice[0] for choice in UserSubscription.STATUS_CHOICES]:
                    user_subscription.status = new_stripe_status

            cps_timestamp = subscription_stripe_obj.get('current_period_start')
            cpe_timestamp = subscription_stripe_obj.get('current_period_end')
            if cps_timestamp is not None:
                user_subscription.current_period_start = datetime.fromtimestamp(
                    cps_timestamp, tz=dt_timezone.utc
                )
            if cpe_timestamp is not None:
                user_subscription.current_period_end = datetime.fromtimestamp(
                    cpe_timestamp, tz=dt_timezone.utc
                )
            user_subscription.cancel_at_period_end = subscription_stripe_obj.get(
                'cancel_at_period_end', False
            )
            if (
                stripe_customer_id_from_sub
                and user_subscription.stripe_customer_id != stripe_customer_id_from_sub
            ):
                user_subscription.stripe_customer_id = stripe_customer_id_from_sub
            user_subscription.save()

            if user_subscription.user:
                if user_subscription.status == 'active' and original_local_status != 'active':
                    if (
                        user_subscription.current_period_start
                        and user_subscription.current_period_end
                    ):
                        send_subscription_confirmation_email_task(user_subscription.id)
                elif (
                    user_subscription.status == 'canceled'
                    and original_local_status != 'canceled'
                ):
                    send_subscription_canceled_email_task(user_subscription.id)
        except UserSubscription.DoesNotExist:
            # Fallback: create a local record using metadata from the Stripe subscription if available
            try:
                metadata = subscription_stripe_obj.get('metadata', {}) or {}
                django_user_id = metadata.get('django_user_id')
                box_type_id = metadata.get('subscription_box_type_id')
                if not (django_user_id and box_type_id):
                    logger.error(
                        "WEBHOOK %s: subscription_id=%s missing metadata to create local record",
                        event_type,
                        stripe_subscription_id,
                    )
                    return HttpResponse(status=200)

                User = get_user_model()
                try:
                    user = User.objects.get(id=int(django_user_id))
                except Exception as e:
                    logger.error(
                        "WEBHOOK %s: cannot resolve user_id=%s for subscription_id=%s: %s",
                        event_type,
                        django_user_id,
                        stripe_subscription_id,
                        e,
                    )
                    return HttpResponse(status=200)

                try:
                    box_type = SubscriptionBoxType.objects.get(id=int(box_type_id))
                except Exception as e:
                    logger.error(
                        "WEBHOOK %s: cannot resolve box_type_id=%s for subscription_id=%s: %s",
                        event_type,
                        box_type_id,
                        stripe_subscription_id,
                        e,
                    )
                    return HttpResponse(status=200)

                # Map Stripe status to local
                mapped_status = 'pending_payment'
                if new_stripe_status == 'active':
                    mapped_status = 'active'
                elif new_stripe_status == 'past_due':
                    mapped_status = 'past_due'
                elif new_stripe_status == 'canceled':
                    mapped_status = 'canceled'
                elif new_stripe_status == 'unpaid':
                    mapped_status = 'past_due'
                elif new_stripe_status == 'trialing':
                    mapped_status = 'trialing'
                elif new_stripe_status in ['incomplete', 'incomplete_expired']:
                    mapped_status = new_stripe_status

                cps_timestamp = subscription_stripe_obj.get('current_period_start')
                cpe_timestamp = subscription_stripe_obj.get('current_period_end')
                cps_dt = (
                    datetime.fromtimestamp(cps_timestamp, tz=dt_timezone.utc)
                    if cps_timestamp is not None
                    else None
                )
                cpe_dt = (
                    datetime.fromtimestamp(cpe_timestamp, tz=dt_timezone.utc)
                    if cpe_timestamp is not None
                    else None
                )

                user_subscription = UserSubscription.objects.create(
                    user=user,
                    box_type=box_type,
                    stripe_subscription_id=stripe_subscription_id,
                    stripe_customer_id=stripe_customer_id_from_sub,
                    status=mapped_status,
                    current_period_start=cps_dt,
                    current_period_end=cpe_dt,
                    cancel_at_period_end=subscription_stripe_obj.get('cancel_at_period_end', False),
                )
                logger.info(
                    "WEBHOOK %s: created missing UserSubscription id=%s for stripe_subscription_id=%s",
                    event_type,
                    user_subscription.id,
                    stripe_subscription_id,
                )
                # Don't send emails here; invoice.paid and deleted handlers will do it to avoid duplicates.
            except Exception as e:
                logger.exception(
                    "WEBHOOK %s: failed to create missing local subscription for stripe_subscription_id=%s: %s",
                    event_type,
                    stripe_subscription_id,
                    e,
                )
                return HttpResponse(status=500)
        except Exception as e:
            logger.exception(
                "WEBHOOK %s: failed to process for Stripe sub ID %s: %s",
                event_type,
                stripe_subscription_id,
                e,
            )
            return HttpResponse(status=500)

    elif event_type == 'invoice.paid':
        invoice = event['data']['object']
        stripe_subscription_id_from_invoice = None

        # Prefer modern top-level field first
        stripe_subscription_id_from_invoice = invoice.get('subscription')

        # Fallbacks for legacy/expanded payloads
        if not stripe_subscription_id_from_invoice:
            parent_details_on_invoice = invoice.get('parent', {}).get(
                'subscription_details', {}
            )
            if parent_details_on_invoice:
                stripe_subscription_id_from_invoice = parent_details_on_invoice.get(
                    'subscription'
                )

        if (
            not stripe_subscription_id_from_invoice
            and invoice.lines
            and invoice.lines.data
        ):
            for line_item_iter in invoice.lines.data:
                subscription_item_details = line_item_iter.get('parent', {}).get(
                    'subscription_item_details', {}
                )
                if (
                    subscription_item_details
                    and subscription_item_details.get('subscription')
                ):
                    stripe_subscription_id_from_invoice = subscription_item_details.get(
                        'subscription'
                    )
                    break

        invoice_id = invoice.get('id')
        invoice_status = invoice.get('status')
        billing_reason = invoice.get('billing_reason')
        logger.info(
            "WEBHOOK invoice.paid: invoice_id=%s subscription_id=%s status=%s billing_reason=%s",
            invoice_id,
            stripe_subscription_id_from_invoice,
            invoice_status,
            billing_reason,
        )

        if invoice_status == 'paid' and stripe_subscription_id_from_invoice:
            try:
                user_subscription = UserSubscription.objects.get(
                    stripe_subscription_id=stripe_subscription_id_from_invoice
                )
                new_period_start_dt = None
                new_period_end_dt = None
                if invoice.lines and invoice.lines.data:
                    target_line_item = None
                    for line_item_iter in invoice.lines.data:
                        line_sub_id_in_item = (
                            line_item_iter.get('parent', {})
                            .get('subscription_item_details', {})
                            .get('subscription')
                        )
                        if line_sub_id_in_item == stripe_subscription_id_from_invoice:
                            target_line_item = line_item_iter
                            break
                    if target_line_item and target_line_item.get('period'):
                        period_data = target_line_item.get('period')
                        new_period_start_ts = period_data.get('start')
                        new_period_end_ts = period_data.get('end')
                        if new_period_start_ts is not None:
                            new_period_start_dt = datetime.fromtimestamp(
                                new_period_start_ts, tz=dt_timezone.utc
                            )
                        if new_period_end_ts is not None:
                            new_period_end_dt = datetime.fromtimestamp(
                                new_period_end_ts, tz=dt_timezone.utc
                            )

                        changed_period = False
                        if new_period_start_dt:
                            if (
                                not user_subscription.current_period_start
                                or new_period_start_dt
                                >= user_subscription.current_period_start
                            ):
                                user_subscription.current_period_start = (
                                    new_period_start_dt
                                )
                                changed_period = True
                        if new_period_end_dt:
                            if (
                                not user_subscription.current_period_end
                                or new_period_end_dt
                                >= user_subscription.current_period_end
                            ):
                                user_subscription.current_period_end = (
                                    new_period_end_dt
                                )
                                changed_period = True
                        if changed_period:
                            logger.info(
                                "WEBHOOK invoice.paid: period updated for UserSubscription id=%s",
                                user_subscription.id,
                            )

                if user_subscription.status in ['incomplete', 'past_due', 'pending_payment']:
                    user_subscription.status = 'active'
                    if (
                        billing_reason == 'subscription_create'
                        and user_subscription.user
                        and user_subscription.current_period_end
                    ):
                        send_subscription_confirmation_email_task(user_subscription.id)

                current_stripe_customer_id = invoice.get('customer')
                if user_subscription.user and current_stripe_customer_id:
                    if not user_subscription.stripe_customer_id:
                        user_subscription.stripe_customer_id = current_stripe_customer_id
                    profile, _ = Profile.objects.get_or_create(
                        user=user_subscription.user
                    )
                    if not profile.stripe_customer_id:
                        profile.stripe_customer_id = current_stripe_customer_id
                        profile.save()

                user_subscription.save()
            except UserSubscription.DoesNotExist:
                logger.warning(
                    "WEBHOOK invoice.paid: UserSubscription for subscription_id=%s NOT FOUND for invoice_id=%s (race condition)",
                    stripe_subscription_id_from_invoice,
                    invoice_id,
                )
            except Exception as e:
                logger.exception(
                    "WEBHOOK invoice.paid: failed to process for sub_id=%s invoice_id=%s: %s",
                    stripe_subscription_id_from_invoice,
                    invoice_id,
                    e,
                )
                return HttpResponse(status=500)
        else:
            logger.info(
                "WEBHOOK invoice.paid: skipped invoice_id=%s (status=%s or subscription_id missing)",
                invoice_id,
                invoice_status,
            )

    elif event_type == 'invoice.payment_failed':
        invoice = event['data']['object']
        stripe_subscription_id_from_invoice = None

        # Prefer modern top-level field first
        stripe_subscription_id_from_invoice = invoice.get('subscription')

        # Fallbacks for legacy/expanded payloads
        if not stripe_subscription_id_from_invoice:
            parent_details_on_invoice = invoice.get('parent', {}).get(
                'subscription_details', {}
            )
            if parent_details_on_invoice:
                stripe_subscription_id_from_invoice = parent_details_on_invoice.get(
                    'subscription'
                )
        if (
            not stripe_subscription_id_from_invoice
            and invoice.lines
            and invoice.lines.data
        ):
            for line_item_iter in invoice.lines.data:
                subscription_item_details = line_item_iter.get('parent', {}).get(
                    'subscription_item_details', {}
                )
                if (
                    subscription_item_details
                    and subscription_item_details.get('subscription')
                ):
                    stripe_subscription_id_from_invoice = subscription_item_details.get(
                        'subscription'
                    )
                    break

        invoice_id = invoice.get('id')
        logger.info(
            "WEBHOOK invoice.payment_failed: subscription_id=%s invoice_id=%s",
            stripe_subscription_id_from_invoice,
            invoice_id,
        )
        if stripe_subscription_id_from_invoice:
            try:
                user_subscription = UserSubscription.objects.get(
                    stripe_subscription_id=stripe_subscription_id_from_invoice
                )
                if user_subscription.status != 'canceled':
                    user_subscription.status = 'past_due'
                    user_subscription.save()
                    if user_subscription.user:
                        send_payment_failed_email_task(user_subscription.id)
            except UserSubscription.DoesNotExist:
                logger.warning(
                    "WEBHOOK invoice.payment_failed: event for non-existent subscription_id=%s",
                    stripe_subscription_id_from_invoice,
                )
            except Exception as e:
                logger.exception(
                    "WEBHOOK invoice.payment_failed: failed to process subscription_id=%s: %s",
                    stripe_subscription_id_from_invoice,
                    e,
                )
                return HttpResponse(status=500)
        else:
            logger.info(
                "WEBHOOK invoice.payment_failed: invoice_id=%s without subscription id",
                invoice_id,
            )

    elif event_type == 'customer.subscription.deleted':
        subscription_stripe_obj = event['data']['object']
        stripe_subscription_id = subscription_stripe_obj.id
        logger.info(
            "WEBHOOK customer.subscription.deleted: subscription_id=%s",
            stripe_subscription_id,
        )
        try:
            user_subscription = UserSubscription.objects.get(
                stripe_subscription_id=stripe_subscription_id
            )
            original_local_status = user_subscription.status
            user_subscription.status = 'canceled'
            user_subscription.save()
            if original_local_status != 'canceled' and user_subscription.user:
                send_subscription_canceled_email_task(user_subscription.id)
        except UserSubscription.DoesNotExist:
            logger.warning(
                "WEBHOOK customer.subscription.deleted: event for non-existent subscription_id=%s",
                stripe_subscription_id,
            )
        except Exception as e:
            logger.exception(
                "WEBHOOK customer.subscription.deleted: failed to process subscription_id=%s: %s",
                stripe_subscription_id,
                e,
            )
            return HttpResponse(status=500)

    else:
        logger.info("WEBHOOK: unhandled event type: %s", event_type)

    return HttpResponse(status=200)
