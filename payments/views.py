# payments/views.py
from django.db.models import F # <--- Импорт для атомарных обновлений
from django.db import transaction 
import stripe # Импортируем библиотеку Stripe
from decimal import Decimal # Для работы с ценами
from django.conf import settings # Для доступа к ключам API и другим настройкам
from django.shortcuts import render, redirect, reverse # get_object_or_404 removed F401
from store.models import Product, Order, OrderItem, SubscriptionBoxType, Profile, UserSubscription # Импортируем модель Order (пока не используем, но понадобится)
from store.cart import Cart # Импортируем нашу корзину
from django.contrib import messages
from django.http import HttpResponse # Для отправки ответа Stripe
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from store.forms import OrderCreateForm
from .tasks import send_order_confirmation_email_task, send_subscription_confirmation_email_task, \
                   send_subscription_canceled_email_task, send_payment_failed_email_task
# from django.utils import timezone # F401 unused import
from datetime import datetime, timezone as dt_timezone
import traceback

stripe.api_key = settings.STRIPE_SECRET_KEY

def checkout_and_payment(request):
    """
    Обрабатывает GET (показ формы адреса) и POST (проверка адреса + создание сессии Stripe).
    """
    cart = Cart(request)
    if len(cart) == 0:
        messages.error(request, "Ваша корзина пуста.")
        return redirect('store:product_list')

    if request.method == 'POST':
        # --- Обработка POST запроса (отправка формы адреса) ---
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            # Форма валидна, данные адреса корректны
            order_details = form.cleaned_data # Получаем проверенные данные формы

            # --- Создаем сессию Stripe ---
            success_url = request.build_absolute_uri(reverse('payments:completed'))
            cancel_url = request.build_absolute_uri(reverse('payments:canceled'))

            session_data = {
                'mode': 'payment',
                'success_url': success_url,
                'cancel_url': cancel_url,
                'line_items': [],
                # Передаем email клиента в Stripe
                'customer_email': order_details['email'],
                 # Важно: НЕ используем client_reference_id, передадим user_id в метаданных
                 # 'client_reference_id': request.user.id if request.user.is_authenticated else None,
                # --- Добавляем МЕТАДАННЫЕ ---
                'metadata': {
                    # Передаем ID пользователя (если есть)
                    'user_id': str(request.user.id) if request.user.is_authenticated else None,
                    # Передаем детали адреса
                    'first_name': order_details['first_name'],
                    'last_name': order_details['last_name'],
                    'address_line_1': order_details['address_line_1'],
                    'address_line_2': order_details['address_line_2'],
                    'postal_code': order_details['postal_code'],
                    'city': order_details['city'],
                    'country': order_details['country'],
                    # Важно: Не передавайте сюда сложные объекты или слишком много данных
                    # Значения должны быть строками, ключи - тоже строки
                }
                # -----------------------------
            }

            # Заполняем line_items (как и раньше, но без expand)
            for item in cart:
                product_data = item['product_obj']
                session_data['line_items'].append({
                    'price_data': {
                        'unit_amount': int(item['price'] * Decimal('100')),
                        'currency': 'pln',
                        'product_data': {
                            'name': product_data.name,
                            'metadata': {'product_db_id': product_data.id}
                        },
                    },
                    'quantity': item['quantity'],
                })

            try:
                # Проверяем минимальную сумму перед созданием сессии
                total_pln = cart.get_total_price()
                if total_pln < Decimal('2.00'): # Минимальная сумма для PLN в Stripe = 2.00
                     messages.error(request, f"Минимальная сумма заказа для оплаты составляет 2.00 PLN. Ваша текущая сумма: {total_pln} PLN.")
                     # Возвращаем пользователя к форме с ошибкой
                     return render(request, 'payments/checkout.html', {'cart': cart, 'form': form})

                session = stripe.checkout.Session.create(**session_data)
                # Перенаправляем на оплату
                return redirect(session.url, code=303)

            except stripe.error.StripeError as e:
                print(f"Stripe Error creating session: {e}")
                messages.error(request, f"Ошибка платежной системы: {e}. Попробуйте снова.")
                # Возвращаем пользователя к форме с ошибкой
                return render(request, 'payments/checkout.html', {'cart': cart, 'form': form})
            except Exception as e:
                print(f"Generic Error creating session: {e}")
                messages.error(request, "Произошла непредвиденная ошибка при создании платежной сессии.")
                return render(request, 'payments/checkout.html', {'cart': cart, 'form': form})

        # Если форма НЕ валидна, остаемся на странице и показываем ошибки
        else:
            messages.error(request, "Пожалуйста, исправьте ошибки в форме адреса.")
            # Форма с ошибками будет передана в рендер ниже

    else:
        # --- Обработка GET запроса (первый заход на страницу) ---
        # Создаем пустую форму или предзаполняем данными пользователя
        initial_data = {}
        if request.user.is_authenticated:
            initial_data = {
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
                # Можно добавить адрес из профиля пользователя, если он есть
            }
        form = OrderCreateForm(initial=initial_data)

    # Рендерим шаблон для GET запроса или если форма была невалидна в POST
    context = {
        'cart': cart,
        'form': form
    }
    return render(request, 'payments/checkout.html', context)

def payment_completed(request):
    """
    Представление для страницы успешной оплаты.
    Может очищать корзину для немедленной обратной связи.
    Основная логика создания заказа теперь в вебхуке.
    """
    # Опционально: очищаем корзину здесь для пользователя
    cart = Cart(request)
    cart.clear()

    # Просто отображаем страницу успеха
    # Передавать 'order' сюда больше не нужно,
    # т.к. мы не знаем наверняка, обработан ли уже вебхук
    return render(request, 'payments/completed.html')

def payment_canceled(request):
    """
    Представление для страницы отмененной оплаты.
    """
    return render(request, 'payments/canceled.html')

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET # Убедитесь, что это STRIPE_WEBHOOK_SECRET, а не другой
    event = None

    print(f"WEBHOOK: Received a request. Sig_header: {sig_header is not None}")

    if not endpoint_secret:
        print("!!! WEBHOOK Error: Stripe Webhook Secret (STRIPE_WEBHOOK_SECRET) not configured.")
        return HttpResponse(status=500, content="Webhook secret not configured.")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        print(f"WEBHOOK ValueError (Invalid payload): {e}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        print(f"WEBHOOK SignatureVerificationError (Invalid signature): {e}")
        return HttpResponse(status=400)
    except Exception as e:
        print(f"WEBHOOK Error (Unknown error during event construction): {e}")
        traceback.print_exc()
        return HttpResponse(status=500)

    print(f"WEBHOOK: Successfully constructed event: id={event.get('id')}, type={event.get('type')}")

    # === Обработчик checkout.session.completed ===
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        session_id = session.id
        session_mode = session.get('mode')
        session_payment_status = session.get('payment_status')
        print(f"WEBHOOK checkout.session.completed: Processing session_id={session_id}, mode={session_mode}, payment_status={session_payment_status}")

        if session_payment_status == "paid":
            if session_mode == 'subscription':
                try:
                    stripe_subscription_id_from_session = session.get('subscription')
                    print(f"WEBHOOK checkout.session.completed (subscription): stripe_subscription_id_from_session='{stripe_subscription_id_from_session}'")

                    # Проверка на идемпотентность, если запись уже была создана этим же subscription_id
                    # (например, если Stripe повторно прислал checkout.session.completed)
                    if stripe_subscription_id_from_session and \
                       UserSubscription.objects.filter(stripe_subscription_id=stripe_subscription_id_from_session).exists():
                        existing_sub = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id_from_session)
                        print(f"WEBHOOK checkout.session.completed (subscription): UserSubscription for Stripe subscription '{stripe_subscription_id_from_session}' (local id {existing_sub.id}) already exists. Idempotency check passed.")
                        # Если запись уже есть, мы все равно можем обновить некоторые поля, если это первое событие,
                        # или просто вернуть 200. Для простоты, если она есть, считаем, что все уже сделано ранее.
                        # Однако, если статус был 'incomplete', его можно обновить.
                        # В данном случае, мы создаем с 'incomplete', так что это не должно быть проблемой.
                        return HttpResponse(status=200)

                    metadata = session.get('metadata', {})
                    django_user_id = metadata.get('django_user_id')
                    box_type_id = metadata.get('subscription_box_type_id')
                    stripe_customer_id = session.get('customer')

                    print(f"WEBHOOK checkout.session.completed (subscription): metadata={metadata}, django_user_id='{django_user_id}', box_type_id='{box_type_id}', stripe_customer_id='{stripe_customer_id}'")

                    if not all([django_user_id, box_type_id, stripe_subscription_id_from_session, stripe_customer_id]):
                        print(f"WEBHOOK checkout.session.completed (subscription) ERROR: Missing required data. UserID: {django_user_id}, BoxTypeID: {box_type_id}, StripeSubID: {stripe_subscription_id_from_session}, StripeCustID: {stripe_customer_id}. Session_id: {session_id}.")
                        return HttpResponse(status=400, content="Missing required data in webhook for subscription session.")

                    User = get_user_model()
                    user = None
                    if django_user_id and django_user_id != 'None':
                        try:
                            user = User.objects.get(id=int(django_user_id))
                            print(f"WEBHOOK checkout.session.completed (subscription): Found user id={user.id}")
                        except (User.DoesNotExist, ValueError, TypeError) as e:
                            print(f"WEBHOOK checkout.session.completed (subscription) WARNING: User with id='{django_user_id}' not found for session {session_id}. Error: {e}")
                            return HttpResponse(status=400, content=f"User with id='{django_user_id}' not found.")
                    
                    if not user:
                        print(f"WEBHOOK checkout.session.completed (subscription) ERROR: User is required for subscription session {session_id}. No valid user found.")
                        return HttpResponse(status=400, content="User is required for subscription.")

                    try:
                        box_type = SubscriptionBoxType.objects.get(id=int(box_type_id))
                        print(f"WEBHOOK checkout.session.completed (subscription): Found box_type id={box_type.id}, name='{box_type.name}'")
                    except (SubscriptionBoxType.DoesNotExist, ValueError, TypeError): # Добавлены ValueError, TypeError
                        print(f"WEBHOOK checkout.session.completed (subscription) ERROR: SubscriptionBoxType with id='{box_type_id}' not found or invalid ID for session {session_id}.")
                        return HttpResponse(status=400, content=f"SubscriptionBoxType with id='{box_type_id}' not found or invalid.")

                    with transaction.atomic():
                        profile, profile_created = Profile.objects.get_or_create(user=user)
                        if not profile.stripe_customer_id:
                            profile.stripe_customer_id = stripe_customer_id
                            profile.save()
                            print(f"WEBHOOK checkout.session.completed (subscription): Profile for user {user.id} {'created' if profile_created else 'retrieved'}. Stripe customer ID set to '{stripe_customer_id}'.")
                        else:
                             print(f"WEBHOOK checkout.session.completed (subscription): Profile for user {user.id} {'created' if profile_created else 'retrieved'}. Stripe customer ID already '{profile.stripe_customer_id}'.")
                        
                        subscription, sub_created = UserSubscription.objects.update_or_create(
                            stripe_subscription_id=stripe_subscription_id_from_session,
                            defaults={
                                'user': user,
                                'box_type': box_type,
                                'stripe_customer_id': stripe_customer_id,
                                'status': 'incomplete', # Начальный статус. Будет обновлен customer.subscription.updated/created или invoice.paid.
                            }
                        )
                        action = "CREATED" if sub_created else "UPDATED (idempotency)"
                        print(f"WEBHOOK checkout.session.completed (subscription): UserSubscription record {action} for Stripe sub ID '{stripe_subscription_id_from_session}', local id={subscription.id}. Status set to 'incomplete'.")
                    
                    print(f"WEBHOOK checkout.session.completed (subscription): Session {session_id} processed successfully.")
                
                except Exception as e:
                    print(f"WEBHOOK checkout.session.completed (subscription) ERROR: Failed to process PAID subscription session {session_id}. Error: {e}")
                    traceback.print_exc()
                    return HttpResponse(status=500)

            elif session_mode == 'payment':
                # ВАШ СУЩЕСТВУЮЩИЙ КОД ДЛЯ ОБРАБОТКИ ОБЫЧНЫХ ПЛАТЕЖЕЙ (session_mode == 'payment')
                # Я его не буду полностью копировать сюда, так как мы фокусировались на подписках,
                # но он должен остаться здесь.
                # Убедитесь, что он использует transaction.atomic() и корректно обрабатывает ошибки.
                try:
                    if Order.objects.filter(stripe_id=session_id).exists():
                        print(f"WEBHOOK checkout.session.completed (payment): Order for payment session {session_id} already exists. Skipping.")
                        return HttpResponse(status=200)

                    metadata = session.get('metadata', {})
                    User = get_user_model()
                    user = None
                    user_id_from_metadata = metadata.get('user_id')
                    print(f"WEBHOOK checkout.session.completed (payment): metadata={metadata}, user_id_from_metadata='{user_id_from_metadata}'")

                    if user_id_from_metadata and user_id_from_metadata != 'None':
                        try:
                            user = User.objects.get(id=int(user_id_from_metadata))
                            print(f"WEBHOOK checkout.session.completed (payment): Found user id={user.id if user else 'None'}")
                        except (User.DoesNotExist, ValueError, TypeError):
                            user = None 
                            print(f"WEBHOOK checkout.session.completed (payment) WARNING: User with id='{user_id_from_metadata}' not found.")
                    
                    customer_details_email = session.get('customer_details', {}).get('email')
                    order_email = customer_details_email if customer_details_email else metadata.get('email', '')
                    print(f"WEBHOOK checkout.session.completed (payment): Order email will be '{order_email}'. Fetching line items for session {session_id}...")
                    
                    try:
                        line_items_response = stripe.checkout.Session.list_line_items(session_id, limit=50, expand=['data.price.product'])
                        if not line_items_response or not line_items_response.data:
                            print(f"WEBHOOK checkout.session.completed (payment) ERROR: Could not retrieve line items for session {session_id}")
                            return HttpResponse(status=500, content="Could not retrieve line items from Stripe.")
                        print(f"WEBHOOK checkout.session.completed (payment): Line items fetched: {len(line_items_response.data)} items.")
                    except stripe.error.StripeError as e:
                        print(f"WEBHOOK checkout.session.completed (payment) ERROR: Stripe API error fetching line items for session {session_id}: {e}")
                        return HttpResponse(status=500)

                    with transaction.atomic():
                        order = Order.objects.create(
                            user=user, paid=True, stripe_id=session_id,
                            first_name=metadata.get('first_name', ''), last_name=metadata.get('last_name', ''),
                            email=order_email, address_line_1=metadata.get('address_line_1', ''),
                            address_line_2=metadata.get('address_line_2', ''), postal_code=metadata.get('postal_code', ''),
                            city=metadata.get('city', ''), country=metadata.get('country', '')
                        )
                        print(f"WEBHOOK checkout.session.completed (payment): Order object created with id={order.id}, stripe_id={order.stripe_id}")
                        items_to_create = []
                        products_stock_update = {}
                        for item_data in line_items_response.data:
                            try:
                                price_info = item_data.get('price', {})
                                product_info_stripe = price_info.get('product', {}) 
                                stripe_product_metadata = product_info_stripe.get('metadata', {})
                                product_db_id_str = stripe_product_metadata.get('product_db_id')

                                if not product_db_id_str:
                                    print(f"WEBHOOK checkout.session.completed (payment) ERROR: Line item from Stripe Product '{product_info_stripe.get('id', 'N/A')}' does not contain 'product_db_id'. Metadata: {stripe_product_metadata}.")
                                    raise ValueError(f"Missing product_db_id for Stripe Product {product_info_stripe.get('id')}")
                                
                                product_db = Product.objects.get(id=int(product_db_id_str))
                                quantity = item_data.get('quantity', 0)
                                unit_amount = price_info.get('unit_amount')
                                if unit_amount is None: unit_amount = item_data.get('amount_subtotal',0) # amount_subtotal для line_item - это цена за единицу * кол-во, до скидок
                                
                                price_paid_per_unit = Decimal(0)
                                if quantity > 0 and unit_amount is not None: # Используем unit_amount если есть, или item_data.price.unit_amount
                                    price_paid_per_unit = (Decimal(price_info.get('unit_amount', item_data.get('amount_subtotal',0) / quantity )) / Decimal('100')) if price_info.get('unit_amount') is not None else (Decimal(item_data.get('amount_subtotal',0))/quantity / Decimal('100'))


                                items_to_create.append(OrderItem(
                                    order=order, product=product_db, price=price_paid_per_unit, quantity=quantity
                                ))
                                products_stock_update[product_db.id] = products_stock_update.get(product_db.id, 0) + quantity
                                print(f"WEBHOOK checkout.session.completed (payment): Prepared OrderItem: product_id={product_db.id}, qty={quantity}, price_per_unit={price_paid_per_unit}")
                            except Product.DoesNotExist:
                                print(f"WEBHOOK checkout.session.completed (payment) ERROR: Product with id={product_db_id_str} not found. Order {order.id} creation failed.")
                                raise 
                            except Exception as e:
                                print(f"WEBHOOK checkout.session.completed (payment) ERROR: Problem processing payment line item for order {order.id}: {e}")
                                traceback.print_exc()
                                raise 
                        if items_to_create: 
                            OrderItem.objects.bulk_create(items_to_create)
                            print(f"WEBHOOK checkout.session.completed (payment): Bulk created {len(items_to_create)} OrderItems for order {order.id}.")
                        for prod_id, qty_decrement in products_stock_update.items():
                            Product.objects.filter(id=prod_id).update(stock=F('stock') - qty_decrement)
                            print(f"WEBHOOK checkout.session.completed (payment): Updated stock for product_id={prod_id}, decrement={qty_decrement}.")
                    print(f"WEBHOOK checkout.session.completed (payment): Order {order.id} successfully processed from webhook for session {session_id}")
                    send_order_confirmation_email_task(order.id)
                    print(f"WEBHOOK checkout.session.completed (payment): Queued order confirmation email for order {order.id}")
                except Exception as e:
                    print(f"WEBHOOK checkout.session.completed (payment) ERROR: Failed to process PAID payment session {session_id}. Error: {e}")
                    traceback.print_exc()
                    return HttpResponse(status=500)

            else: # session_mode не 'subscription' и не 'payment'
                print(f"WEBHOOK checkout.session.completed ERROR: Unknown session mode '{session_mode}' for session {session_id}")
                return HttpResponse(status=400, content="Unknown session mode.")
        else: # payment_status != "paid"
             print(f"WEBHOOK checkout.session.completed: Payment status for session {session_id} is '{session_payment_status}', not processing.")

    # === Обработчик customer.subscription.created И customer.subscription.updated ===
    elif event['type'] in ['customer.subscription.created', 'customer.subscription.updated']:
        subscription_stripe_obj = event['data']['object']
        stripe_subscription_id = subscription_stripe_obj.id
        new_stripe_status = subscription_stripe_obj.get('status')
        stripe_customer_id_from_sub = subscription_stripe_obj.get('customer')

        print(f"WEBHOOK {event['type']}: Processing for Stripe subscription ID: '{stripe_subscription_id}', New Stripe Status: '{new_stripe_status}'")

        try:
            # Пытаемся ПОЛУЧИТЬ существующую UserSubscription.
            # Она ДОЛЖНА быть создана ранее обработчиком checkout.session.completed.
            user_subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)
            print(f"WEBHOOK {event['type']}: Found UserSubscription id={user_subscription.id}. Old local status: {user_subscription.status}")

            original_local_status = user_subscription.status

            # Обновляем статус из Stripe
            if new_stripe_status == 'active': user_subscription.status = 'active'
            elif new_stripe_status == 'past_due': user_subscription.status = 'past_due'
            elif new_stripe_status == 'canceled': user_subscription.status = 'canceled'
            elif new_stripe_status == 'unpaid': user_subscription.status = 'past_due' 
            elif new_stripe_status == 'trialing': user_subscription.status = 'trialing'
            elif new_stripe_status in ['incomplete', 'incomplete_expired']:
                if new_stripe_status in [choice[0] for choice in UserSubscription.STATUS_CHOICES]: # Проверяем, есть ли такой статус в нашей модели
                    user_subscription.status = new_stripe_status
            
            print(f"WEBHOOK {event['type']}: New local status for sub id {user_subscription.id} will be: {user_subscription.status}")

            # Обновляем период
            cps_timestamp = subscription_stripe_obj.get('current_period_start')
            cpe_timestamp = subscription_stripe_obj.get('current_period_end')

            if cps_timestamp is not None:
                user_subscription.current_period_start = datetime.fromtimestamp(cps_timestamp, tz=dt_timezone.utc)
            # else: # Не логируем здесь, чтобы не засорять, если это норма для .created без периода
                # print(f"WEBHOOK {event['type']}: 'current_period_start' is None for Stripe subscription '{stripe_subscription_id}'.") 
            
            if cpe_timestamp is not None:
                user_subscription.current_period_end = datetime.fromtimestamp(cpe_timestamp, tz=dt_timezone.utc)
            # else:
                # print(f"WEBHOOK {event['type']}: 'current_period_end' is None for Stripe subscription '{stripe_subscription_id}'.")
            
            user_subscription.cancel_at_period_end = subscription_stripe_obj.get('cancel_at_period_end', False)
            
            if stripe_customer_id_from_sub and user_subscription.stripe_customer_id != stripe_customer_id_from_sub:
                user_subscription.stripe_customer_id = stripe_customer_id_from_sub
            
            user_subscription.save()
            print(f"WEBHOOK {event['type']}: UserSubscription id={user_subscription.id} updated. New local status: {user_subscription.status}, period_start: {user_subscription.current_period_start}, period_end: {user_subscription.current_period_end}, cancel_at_period_end: {user_subscription.cancel_at_period_end}.")

            # Отправка писем (только если статус действительно изменился и есть пользователь)
            if user_subscription.user:
                if user_subscription.status == 'active' and original_local_status != 'active':
                    # Отправляем письмо о подтверждении/активации, ТОЛЬКО если период УЖЕ установлен
                    if user_subscription.current_period_start and user_subscription.current_period_end:
                        send_subscription_confirmation_email_task(user_subscription.id)
                        print(f"WEBHOOK {event['type']}: Queued subscription confirmation email for UserSubscription id={user_subscription.id} (status became active and period is set).")
                    else:
                        # Если подписка стала активной, но период еще не пришел (маловероятно из customer.subscription.updated, но возможно для .created)
                        # то письмо о подтверждении лучше отложить до момента, когда период будет известен (например, из invoice.paid).
                        # Или, если статус 'active' уже подразумевает наличие периода от Stripe, то все ок.
                        print(f"WEBHOOK {event['type']}: UserSubscription id={user_subscription.id} became active, but period might not be set yet. Confirmation email logic might need review if period comes later.")
                elif user_subscription.status == 'canceled' and original_local_status != 'canceled':
                    send_subscription_canceled_email_task(user_subscription.id)
                    print(f"WEBHOOK {event['type']}: Queued subscription canceled email for UserSubscription id={user_subscription.id}")

        except UserSubscription.DoesNotExist:
            print(f"WEBHOOK {event['type']} CRITICAL ERROR: UserSubscription with stripe_subscription_id='{stripe_subscription_id}' NOT FOUND. This should have been created by checkout.session.completed. This event for subscription '{stripe_subscription_id}' cannot be processed without a prior UserSubscription record.")
            # Возвращаем 200, чтобы не блокировать Stripe для этого события, т.к. мы не можем его исправить без данных из checkout.session.
            # Проблема должна быть решена на уровне гарантии обработки checkout.session.completed.
        except Exception as e:
            print(f"WEBHOOK {event['type']} ERROR: Failed to process for Stripe sub ID '{stripe_subscription_id}'. Error: {e}")
            traceback.print_exc()
            return HttpResponse(status=500)

    # === Обработчик invoice.paid ===
    # Основная задача - обновить период, если он новее, и подтвердить статус 'active'
    # Не должен создавать UserSubscription, если ее нет для billing_reason = subscription_create
    elif event['type'] == 'invoice.paid':
        invoice = event['data']['object']
        stripe_subscription_id_from_invoice = None # Используем новое имя переменной

        # Попытка 1: из invoice.subscription (если Stripe изменит структуру и добавит его)
        # stripe_subscription_id_from_invoice = invoice.get('subscription') # Маловероятно, что появится, если уже нет

        # Попытка 2: из invoice.parent.subscription_details.subscription
        if not stripe_subscription_id_from_invoice:
            parent_details_on_invoice = invoice.get('parent', {}).get('subscription_details', {})
            if parent_details_on_invoice:
                stripe_subscription_id_from_invoice = parent_details_on_invoice.get('subscription')
        
        # Попытка 3: из первой строки инвойса
        if not stripe_subscription_id_from_invoice and invoice.lines and invoice.lines.data:
            for line_item_iter in invoice.lines.data: # Перебираем все строки
                subscription_item_details = line_item_iter.get('parent', {}).get('subscription_item_details', {})
                if subscription_item_details and subscription_item_details.get('subscription'):
                    stripe_subscription_id_from_invoice = subscription_item_details.get('subscription')
                    break # Нашли в одной из строк, выходим

        invoice_id = invoice.get('id')
        invoice_status = invoice.get('status')
        billing_reason = invoice.get('billing_reason')

        print(f"WEBHOOK invoice.paid: Final check: invoice_id='{invoice_id}', determined_subscription_id='{stripe_subscription_id_from_invoice}', status='{invoice_status}', billing_reason='{billing_reason}'")

        if invoice_status == 'paid' and stripe_subscription_id_from_invoice:
            try:
                user_subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id_from_invoice)
                print(f"WEBHOOK invoice.paid: Found UserSubscription id={user_subscription.id} for subscription_id='{stripe_subscription_id_from_invoice}'. Current local period_end: {user_subscription.current_period_end}")

                new_period_start_dt = None
                new_period_end_dt = None

                if invoice.lines and invoice.lines.data:
                    target_line_item = None
                    for line_item_iter in invoice.lines.data:
                        line_sub_id_in_item = line_item_iter.get('parent', {}).get('subscription_item_details', {}).get('subscription')
                        if line_sub_id_in_item == stripe_subscription_id_from_invoice:
                            target_line_item = line_item_iter
                            break
                    
                    if target_line_item and target_line_item.get('period'):
                        period_data = target_line_item.get('period')
                        new_period_start_ts = period_data.get('start')
                        new_period_end_ts = period_data.get('end')
                        if new_period_start_ts is not None: new_period_start_dt = datetime.fromtimestamp(new_period_start_ts, tz=dt_timezone.utc)
                        if new_period_end_ts is not None: new_period_end_dt = datetime.fromtimestamp(new_period_end_ts, tz=dt_timezone.utc)
                        print(f"WEBHOOK invoice.paid: Period from invoice line for sub '{stripe_subscription_id_from_invoice}': start='{new_period_start_dt}', end='{new_period_end_dt}'")

                        # Обновляем период в UserSubscription, если он действительно установлен из инвойса
                        # и если он новее (или еще не установлен), чем текущий в БД.
                        # Это важно, чтобы customer.subscription.updated мог иметь приоритет, если он пришел позже с более актуальными данными.
                        changed_period = False
                        if new_period_start_dt:
                            if not user_subscription.current_period_start or new_period_start_dt >= user_subscription.current_period_start: # >= чтобы обработать тот же период
                                user_subscription.current_period_start = new_period_start_dt
                                changed_period = True
                        if new_period_end_dt:
                            if not user_subscription.current_period_end or new_period_end_dt >= user_subscription.current_period_end:
                                user_subscription.current_period_end = new_period_end_dt
                                changed_period = True
                        if changed_period:
                             print(f"WEBHOOK invoice.paid: Period updated for UserSubscription id={user_subscription.id}.")
                        else:
                             print(f"WEBHOOK invoice.paid: Period for UserSubscription id={user_subscription.id} not updated from invoice (either no new data or existing data is more recent/same).")
                    else:
                         print(f"WEBHOOK invoice.paid: No relevant period data in invoice line item for subscription '{stripe_subscription_id_from_invoice}'.")
                
                # Если статус подписки 'incomplete' или 'past_due', и пришел оплаченный инвойс, переводим в 'active'.
                if user_subscription.status in ['incomplete', 'past_due', 'pending_payment']:
                    user_subscription.status = 'active'
                    print(f"WEBHOOK invoice.paid: Set UserSubscription id={user_subscription.id} status to 'active' due to paid invoice.")
                    # Отправка письма о подтверждении/активации, если это первая активация
                    if billing_reason == 'subscription_create' and user_subscription.user and user_subscription.current_period_end:
                        send_subscription_confirmation_email_task(user_subscription.id)
                        print(f"WEBHOOK invoice.paid: Queued subscription confirmation email for UserSubscription id={user_subscription.id} (status became active after initial invoice).")


                # Обновляем stripe_customer_id, если его нет
                current_stripe_customer_id = invoice.get('customer')
                if user_subscription.user and current_stripe_customer_id:
                    if not user_subscription.stripe_customer_id:
                        user_subscription.stripe_customer_id = current_stripe_customer_id
                    profile, _ = Profile.objects.get_or_create(user=user_subscription.user)
                    if not profile.stripe_customer_id:
                        profile.stripe_customer_id = current_stripe_customer_id
                        profile.save()

                user_subscription.save()
                print(f"WEBHOOK invoice.paid: UserSubscription id={user_subscription.id} SAVED. current_period_end: {user_subscription.current_period_end}, status: {user_subscription.status}")

            except UserSubscription.DoesNotExist:
                print(f"WEBHOOK invoice.paid WARNING: UserSubscription for stripe_subscription_id='{stripe_subscription_id_from_invoice}' NOT FOUND for invoice_id='{invoice_id}'. Race condition likely if billing_reason='subscription_create'.")
            except Exception as e:
                print(f"WEBHOOK invoice.paid ERROR: Failed to process for Stripe sub ID '{stripe_subscription_id_from_invoice}', invoice_id='{invoice_id}'. Error: {e}")
                traceback.print_exc()
                return HttpResponse(status=500)
        else:
            print(f"WEBHOOK invoice.paid: Skipped actual update for invoice_id='{invoice_id}'. Conditions not met: invoice_status='{invoice_status}' or determined_subscription_id='{stripe_subscription_id_from_invoice}' is None.")

    # === Обработчик invoice.payment_failed ===
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        stripe_subscription_id_from_invoice = None
        parent_details_on_invoice = invoice.get('parent', {}).get('subscription_details', {})
        if parent_details_on_invoice: stripe_subscription_id_from_invoice = parent_details_on_invoice.get('subscription')
        if not stripe_subscription_id_from_invoice and invoice.lines and invoice.lines.data:
            for line_item_iter in invoice.lines.data:
                subscription_item_details = line_item_iter.get('parent', {}).get('subscription_item_details', {})
                if subscription_item_details and subscription_item_details.get('subscription'):
                    stripe_subscription_id_from_invoice = subscription_item_details.get('subscription'); break
        
        invoice_id = invoice.get('id')
        print(f"WEBHOOK invoice.payment_failed: Processing for Stripe subscription ID: '{stripe_subscription_id_from_invoice}', Invoice ID: '{invoice_id}'")
        if stripe_subscription_id_from_invoice:
            try:
                user_subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id_from_invoice)
                if user_subscription.status != 'canceled':
                    user_subscription.status = 'past_due'
                    user_subscription.save()
                    print(f"WEBHOOK invoice.payment_failed: UserSubscription id={user_subscription.id} status updated to 'past_due'.")
                    if user_subscription.user:
                        send_payment_failed_email_task(user_subscription.id)
                        print(f"WEBHOOK invoice.payment_failed: Queued payment failed email for UserSubscription id={user_subscription.id}")
                else:
                    print(f"WEBHOOK invoice.payment_failed: UserSubscription id={user_subscription.id} is already 'canceled'. Not changing status.")
            except UserSubscription.DoesNotExist:
                 print(f"WEBHOOK invoice.payment_failed WARNING: Received event for non-existent UserSubscription with Stripe sub ID: '{stripe_subscription_id_from_invoice}'")
            except Exception as e:
                 print(f"WEBHOOK invoice.payment_failed ERROR: Failed to process for Stripe sub ID '{stripe_subscription_id_from_invoice}'. Error: {e}")
                 traceback.print_exc()
                 return HttpResponse(status=500)
        else:
            print(f"WEBHOOK invoice.payment_failed: Event for invoice_id='{invoice_id}' without a discernible subscription ID.")

    # === Обработчик customer.subscription.deleted ===
    elif event['type'] == 'customer.subscription.deleted':
        subscription_stripe_obj = event['data']['object']
        stripe_subscription_id = subscription_stripe_obj.id
        print(f"WEBHOOK customer.subscription.deleted: Processing for Stripe subscription ID: '{stripe_subscription_id}'")
        try:
            user_subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)
            original_local_status = user_subscription.status
            user_subscription.status = 'canceled'
            # if hasattr(user_subscription, 'canceled_at') and user_subscription.canceled_at is None:
            #    user_subscription.canceled_at = timezone.now() # django.utils.timezone
            user_subscription.save()
            print(f"WEBHOOK customer.subscription.deleted: UserSubscription id={user_subscription.id} status set to 'canceled'.")
            if original_local_status != 'canceled' and user_subscription.user:
                send_subscription_canceled_email_task(user_subscription.id)
                print(f"WEBHOOK customer.subscription.deleted: Queued subscription canceled email for UserSubscription id={user_subscription.id}")
        except UserSubscription.DoesNotExist:
            print(f"WEBHOOK customer.subscription.deleted WARNING: Received event for non-existent UserSubscription with Stripe sub ID: '{stripe_subscription_id}'")
        except Exception as e:
            print(f"WEBHOOK customer.subscription.deleted ERROR: Failed to process for Stripe sub ID '{stripe_subscription_id}'. Error: {e}")
            traceback.print_exc()
            return HttpResponse(status=500)
    
    else: # Другие, не обрабатываемые типы событий
        print(f"WEBHOOK: Unhandled event type: {event['type']}")
    
    return HttpResponse(status=200)