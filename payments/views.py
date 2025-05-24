# payments/views.py
from django.db.models import F # <--- Импорт для атомарных обновлений
from django.db import transaction 
import stripe # Импортируем библиотеку Stripe
from decimal import Decimal # Для работы с ценами
from django.conf import settings # Для доступа к ключам API и другим настройкам
from django.shortcuts import render, redirect, reverse, get_object_or_404
from store.models import Product, Order, OrderItem, SubscriptionBoxType, Profile, UserSubscription # Импортируем модель Order (пока не используем, но понадобится)
from store.cart import Cart # Импортируем нашу корзину
from django.contrib import messages
from django.http import HttpResponse # Для отправки ответа Stripe
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from store.forms import OrderCreateForm
from .tasks import send_order_confirmation_email_task, send_subscription_confirmation_email_task, \
                   send_subscription_canceled_email_task, send_payment_failed_email_task
from django.utils import timezone

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
                product_data = item['product']
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
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    event = None

    # Проверка наличия секрета
    if not endpoint_secret:
         print("!!! Webhook Error: Stripe Webhook Secret not configured.")
         return HttpResponse(status=500)

    # Проверка подписи и парсинг события
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        print(f"Webhook ValueError (Invalid payload): {e}")
        return HttpResponse(status=400) # Ошибка в запросе клиента (Stripe)
    except stripe.error.SignatureVerificationError as e:
        print(f"Webhook SignatureVerificationError (Invalid signature): {e}")
        return HttpResponse(status=400) # Ошибка в запросе клиента (Stripe)
    except Exception as e:
        print(f"Webhook Error (Unknown error during event construction): {e}")
        return HttpResponse(status=500) # Неизвестная ошибка сервера

    # Обработка конкретного события checkout.session.completed
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        session_id = session.id
        session_mode = session.get('mode')
        print(f"Processing checkout.session.completed for session: {session.id} with mode: {session_mode}")

        if session.payment_status == "paid":
            if session_mode == 'subscription':
                try:
                    stripe_subscription_id_from_session = session.get('subscription')
                    if stripe_subscription_id_from_session and \
                       UserSubscription.objects.filter(stripe_subscription_id=stripe_subscription_id_from_session).exists():
                        print(f"UserSubscription for Stripe subscription {stripe_subscription_id_from_session} already exists (checked before update_or_create). Skipping further processing for this event.")
                        return HttpResponse(status=200)

                    metadata = session.get('metadata', {})
                    django_user_id = metadata.get('django_user_id')
                    box_type_id = metadata.get('subscription_box_type_id')
                    stripe_subscription_id = session.get('subscription')
                    stripe_customer_id = session.get('customer')

                    if not all([django_user_id, box_type_id, stripe_subscription_id, stripe_customer_id]):
                        print(f"Webhook Error: Missing required metadata for subscription session {session_id}. Metadata: {metadata}")
                        return HttpResponse(status=400)

                    User = get_user_model()
                    user = None
                    if django_user_id and django_user_id != 'None':
                        try:
                            user = User.objects.get(id=int(django_user_id))
                        except (User.DoesNotExist, ValueError, TypeError):
                            print(f"Webhook Warning: User with id='{django_user_id}' not found for subscription session {session_id}.")
                            return HttpResponse(status=400)
                        
                    if not user:
                        print(f"Webhook Error: User is required for subscription session {session_id}. No valid user found.")

                    box_type = get_object_or_404(SubscriptionBoxType, id=box_type_id)

                    with transaction.atomic():
                        # Обновляем или создаем профиль клиента Stripe
                        if user:
                            profile, _ = Profile.objects.get_or_create(user=user)
                            if not profile.stripe_customer_id:
                                profile.stripe_customer_id = stripe_customer_id
                                profile.save()
                            print(f"Profile updated/retrieved for user {user.id} with Stripe customer ID {stripe_customer_id}")

                        # Создаем или обновляем запись о подписке пользователя
                        # (логика может зависеть от того, обрабатываете ли вы customer.subscription.created/updated отдельно)
                        subscription, created = UserSubscription.objects.update_or_create(
                            stripe_subscription_id=stripe_subscription_id,
                            defaults={
                                'user': user,
                                'box_type': box_type,
                                'stripe_customer_id': stripe_customer_id,
                                'status': 'active', # Считаем активной после успешной оплаты
                                # current_period_start/end лучше получать из события customer.subscription.updated или invoice.paid
                            }
                        )
                        if created:
                            print(f"UserSubscription record CREATED for Stripe sub ID {stripe_subscription_id}")
                        else:
                            print(f"UserSubscription record UPDATED for Stripe sub ID {stripe_subscription_id}")
                        if user: # Отправляем письмо, только если есть пользователь с email
                           send_subscription_confirmation_email_task(subscription.id)
                        # Отправляем email с подтверждением подписки

                    print(f"Subscription session {session_id} processed successfully.")
                    return HttpResponse(status=200)

                except Exception as e:
                    print(f"Webhook Error: Failed to process PAID subscription session {session_id}. Error: {e}")
                    return HttpResponse(status=500)

            elif session_mode == 'payment':
                try:
                    if Order.objects.filter(stripe_id=session_id).exists():
                        print(f"Order for payment session {session_id} already exists.")
                        return HttpResponse(status=200)

                    metadata = session.get('metadata', {})
                    User = get_user_model()
                    user = None
                    user_id_from_metadata = metadata.get('user_id')
                    if user_id_from_metadata and user_id_from_metadata != 'None': # Проверка, что не строка "None"
                        try:
                            user = User.objects.get(id=int(user_id_from_metadata))
                        except (User.DoesNotExist, ValueError, TypeError):
                            user = None

                    print(f"Fetching line items for payment session {session_id}...")
                    try:
                        line_items_response = stripe.checkout.Session.list_line_items(
                            session_id, limit=50, expand=['data.price.product']
                        )
                        if not line_items_response or not line_items_response.data:
                            print(f"Webhook Error: Could not retrieve line items for payment session {session_id}")
                            return HttpResponse(status=500)
                        print(f"Line items fetched successfully: {len(line_items_response.data)} items.")
                    except stripe.error.StripeError as e:
                        print(f"Webhook Error: Stripe API error fetching line items for payment session {session_id}: {e}")
                        return HttpResponse(status=500)

                    with transaction.atomic():
                        order = Order.objects.create(
                            user=user,
                            paid=True,
                            stripe_id=session_id,
                            first_name=metadata.get('first_name', ''),
                            last_name=metadata.get('last_name', ''),
                            email=session.customer_details.email if session.customer_details else metadata.get('email', ''),
                            address_line_1=metadata.get('address_line_1', ''),
                            address_line_2=metadata.get('address_line_2', ''),
                            postal_code=metadata.get('postal_code', ''),
                            city=metadata.get('city', ''),
                            country=metadata.get('country', '')
                        )
                        items_to_create = []
                        products_stock_update = {}
                        for item_data in line_items_response.data:
                            try:
                                price_info = item_data.get('price', {})
                                product_info = price_info.get('product', {}) # Это Stripe Product
                                stripe_product_metadata = product_info.get('metadata', {})
                                product_db_id = stripe_product_metadata.get('product_db_id')

                                if not product_db_id:
                                    print(f"Webhook Error: Payment line item from Stripe Product {product_info.id} does not contain product_db_id. Metadata: {stripe_product_metadata}")
                                    raise ValueError("Missing product_db_id in payment line item metadata")

                                product = Product.objects.get(id=product_db_id)
                                quantity = item_data.get('quantity', 0)
                                price_paid = Decimal(item_data.get('amount_total', 0)) / 100 # Используем amount_total для общей суммы позиции
                                                                                            # или item_data.price.unit_amount если это цена за единицу

                                items_to_create.append(OrderItem(
                                    order=order, product=product, price=price_paid / quantity if quantity else 0, quantity=quantity
                                )) # Убедитесь, что price это цена за единицу
                                products_stock_update[product.id] = products_stock_update.get(product.id, 0) + quantity
                            except Product.DoesNotExist:
                                print(f"Webhook Error: Product with id={product_db_id} not found (session {session_id}). Order creation failed.")
                                raise ValueError(f"Product {product_db_id} not found") # Откатит транзакцию
                            except Exception as e:
                                print(f"Webhook Error: Problem processing payment line item: {e}")
                                raise # Откатываем транзакцию

                        if items_to_create: OrderItem.objects.bulk_create(items_to_create)
                        for prod_id, qty_decrement in products_stock_update.items():
                            Product.objects.filter(id=prod_id).update(stock=F('stock') - qty_decrement)

                    print(f"Order {order.id} successfully created from webhook for payment session {session_id}")
                    send_order_confirmation_email_task(order.id) # Используем .delay()
                    return HttpResponse(status=200)

                except Exception as e:
                    print(f"Webhook Error: Failed to process PAID payment session {session_id}. Error: {e}")
                    return HttpResponse(status=500)
            else:
                print(f"Webhook Error: Unknown session mode '{session_mode}' for session {session_id}")
                return HttpResponse(status=400) # Неизвестный режим сессии

        else: # payment_status != "paid"
            print(f"Payment status for session {session_id} is '{session.payment_status}', not creating order/subscription.")
            return HttpResponse(status=200)
        
    elif event['type'] == 'invoice.paid':
        invoice = event['data']['object']
        stripe_subscription_id = invoice.get('subscription')
        stripe_customer_id = invoice.get('customer')
        invoice_id = invoice.get('id') # Более безопасный доступ
        invoice_status = invoice.get('status') # Более безопасный доступ
        # Для boolean 'paid' можно использовать .get() с дефолтным значением
        is_invoice_paid_from_attribute = invoice.get('paid', False) 

        print(f"Processing 'invoice.paid' event for Stripe Invoice ID: {invoice_id}, Subscription ID: {stripe_subscription_id}, Status: {invoice_status}, Paid Flag: {is_invoice_paid_from_attribute}")

        # Обрабатываем, только если счет оплачен и это счет по подписке
        if invoice_status == 'paid' and stripe_subscription_id:
            try:
                user_subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)

                # Обновляем даты периода подписки
                new_period_start = None
                new_period_end = None
                if invoice.lines and invoice.lines.data: # Убедимся, что есть строки в инвойсе
                    # Обычно для подписки одна строка (line item)
                    # Если могут быть другие сценарии (например, инвойс с несколькими строками подписки),
                    # нужно будет более сложная логика для определения правильной строки.
                    # Для простоты берем первую.
                    subscription_line_item = next((line for line in invoice.lines.data if line.type == "subscription" and line.subscription == stripe_subscription_id), None)
                    if subscription_line_item and subscription_line_item.period:
                        period_data = subscription_line_item.period
                        new_period_start = timezone.datetime.fromtimestamp(period_data.start, tz=timezone.utc)
                        new_period_end = timezone.datetime.fromtimestamp(period_data.end, tz=timezone.utc)
                
                if new_period_start and new_period_end:
                    user_subscription.current_period_start = new_period_start
                    user_subscription.current_period_end = new_period_end
                
                user_subscription.status = 'active' # Подтверждаем, что активна
                user_subscription.save()
                
                # Опционально обновить stripe_customer_id в UserSubscription и Profile, если его нет
                if user_subscription.user and stripe_customer_id:
                    if not user_subscription.stripe_customer_id:
                        user_subscription.stripe_customer_id = stripe_customer_id
                        user_subscription.save(update_fields=['stripe_customer_id'])
                    
                    profile, _ = Profile.objects.get_or_create(user=user_subscription.user)
                    if not profile.stripe_customer_id:
                        profile.stripe_customer_id = stripe_customer_id
                        profile.save()
                
                print(f"UserSubscription {user_subscription.id} updated from invoice.paid. Status: active. Period: {new_period_start} - {new_period_end}")
                
                # Опционально: отправить email о продлении подписки (если это не первая оплата)
                # if invoice.billing_reason != 'subscription_create': # Не отправлять для первого инвойса, т.к. уже есть письмо об активации
                #     send_subscription_renewal_email_task.delay(user_subscription.id)

            except UserSubscription.DoesNotExist:
                print(f"Webhook Warning: Received invoice.paid for non-existent UserSubscription with Stripe sub ID: {stripe_subscription_id}")
            except Exception as e:
                print(f"Webhook Error: Failed to process invoice.paid for Stripe sub ID {stripe_subscription_id}. Error: {e}")
                # Не возвращаем 500, чтобы Stripe не повторял, если проблема с нашей стороны, но не критичная для Stripe
        else:
            print(f"Invoice {invoice_id} (status: {invoice_status}) from 'invoice.paid' event not processed further. Might not be related to a known subscription or status is not 'paid'. Billing reason: {invoice.get('billing_reason')}")

        return HttpResponse(status=200)
    
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        stripe_subscription_id = invoice.get('subscription')
        
        print(f"Processing invoice.payment_failed for Stripe subscription ID: {stripe_subscription_id}, Invoice ID: {invoice.id}")

        if stripe_subscription_id:
            try:
                user_subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)
                # Stripe будет пытаться списать средства несколько раз (Smart Retries).
                # Статус 'past_due' уместен, пока Stripe не отменит подписку окончательно.
                user_subscription.status = 'past_due' 
                user_subscription.save()
                print(f"UserSubscription {user_subscription.id} status updated to 'past_due' due to invoice.payment_failed.")
                
                if user_subscription.user:
                    send_payment_failed_email_task(user_subscription.id)
                # Опционально: отправить email пользователю о проблеме с оплатой
                # send_payment_failed_email_task.delay(user_subscription.id)

            except UserSubscription.DoesNotExist:
                print(f"Webhook Warning: Received invoice.payment_failed for non-existent UserSubscription with Stripe sub ID: {stripe_subscription_id}")
            except Exception as e:
                print(f"Webhook Error: Failed to process invoice.payment_failed for Stripe sub ID {stripe_subscription_id}. Error: {e}")
        else:
            print(f"Invoice.payment_failed event {invoice.id} without a subscription ID.")
            
        return HttpResponse(status=200)
    

    elif event['type'] == 'customer.subscription.updated':
        subscription_stripe_obj = event['data']['object']
        stripe_subscription_id = subscription_stripe_obj.id
        
        print(f"Processing customer.subscription.updated for Stripe subscription ID: {stripe_subscription_id}")

        try:
            user_subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)
            
            new_status_from_stripe = subscription_stripe_obj.get('status')
            previous_attributes = event['data'].get('previous_attributes', {}) # Для отслеживания, что именно изменилось
            
            print(f"  Stripe new status: {new_status_from_stripe}, Current local status: {user_subscription.status}")
            if 'status' in previous_attributes:
                 print(f"  Stripe previous status: {previous_attributes['status']}")

            # Простое сопоставление статусов (доработайте при необходимости)
            # Статусы Stripe: active, past_due, unpaid, canceled, incomplete, incomplete_expired, trialing, paused
            # Ваши статусы в UserSubscription.STATUS_CHOICES
            if new_status_from_stripe == 'active':
                user_subscription.status = 'active'
            elif new_status_from_stripe == 'past_due':
                user_subscription.status = 'past_due'
            elif new_status_from_stripe == 'canceled':
                user_subscription.status = 'canceled'
            elif new_status_from_stripe == 'unpaid':
                user_subscription.status = 'past_due' 
            elif new_status_from_stripe == 'trialing':
                user_subscription.status = 'trialing' # Убедитесь, что 'trialing' есть в ваших UserSubscription.STATUS_CHOICES
            elif new_status_from_stripe in ['incomplete', 'incomplete_expired']:
                    # Убедитесь, что эти статусы есть в UserSubscription.STATUS_CHOICES или сопоставьте их
                if new_status_from_stripe in [choice[0] for choice in UserSubscription.STATUS_CHOICES]:
                    user_subscription.status = new_status_from_stripe
                else:
                    print(f"  Stripe status '{new_status_from_stripe}' not directly mapped. Keeping local status '{user_subscription.status}'.")
            else:
                print(f"  Unhandled Stripe subscription status '{new_status_from_stripe}' for UserSubscription {user_subscription.id}. Keeping current local status '{user_subscription.status}'.")

            cps_timestamp = subscription_stripe_obj.get('current_period_start')
            cpe_timestamp = subscription_stripe_obj.get('current_period_end')

            if cps_timestamp is not None: # Проверяем, что значение не None
                user_subscription.current_period_start = timezone.datetime.fromtimestamp(cps_timestamp, tz=timezone.utc)
            else:
                print(f"  Warning: 'current_period_start' is None for Stripe subscription {stripe_subscription_id}.")
                
            if cpe_timestamp is not None: # Проверяем, что значение не None
                user_subscription.current_period_end = timezone.datetime.fromtimestamp(cpe_timestamp, tz=timezone.utc)
            else:
                print(f"  Warning: 'current_period_end' is None for Stripe subscription {stripe_subscription_id}.")
                
                # Безопасно получаем cancel_at_period_end (это boolean)
            user_subscription.cancel_at_period_end = subscription_stripe_obj.get('cancel_at_period_end', False) # False как дефолтное значение
                
                # Проверяем, не нужно ли установить дату отмены, если подписка стала 'canceled'
            if user_subscription.status == 'canceled' and \
                'status' in previous_attributes and \
                previous_attributes.get('status') != 'canceled':
                if hasattr(user_subscription, 'canceled_at') and user_subscription.canceled_at is None: # Если есть поле и оно не установлено
                    user_subscription.canceled_at = timezone.now()
            
            user_subscription.save()
            print(f"UserSubscription {user_subscription.id} updated from customer.subscription.updated. New local status: {user_subscription.status}.")
            if user_subscription.status == 'canceled' and user_subscription.user:
                send_subscription_canceled_email_task(user_subscription.id)
        except UserSubscription.DoesNotExist:
            # Если подписка была создана в Stripe, но не в вашей БД (маловероятно, если checkout.session.completed работает)
            # Можно попытаться создать ее здесь, если есть все данные
            print(f"Webhook Warning: Received customer.subscription.updated for non-existent UserSubscription with Stripe sub ID: {stripe_subscription_id}. Consider creating it if it's a new subscription not caught by checkout.session.completed.")
        except Exception as e:
            print(f"Webhook Error: Failed to process customer.subscription.updated for Stripe sub ID {stripe_subscription_id}. Error: {e}")
        
        return HttpResponse(status=200)
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription_stripe_obj = event['data']['object']
        stripe_subscription_id = subscription_stripe_obj.id

        print(f"Processing customer.subscription.deleted for Stripe subscription ID: {stripe_subscription_id}")

        try:
            user_subscription = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)
            user_subscription.status = 'canceled' # Подписка удалена = отменена
            # Можно также обнулить current_period_end или установить дату отмены
            user_subscription.canceled_at = timezone.now() # Если у вас есть такое поле
            user_subscription.save()
            print(f"UserSubscription {user_subscription.id} status set to 'canceled' due to customer.subscription.deleted.")
            if user_subscription.user:
                send_subscription_canceled_email_task(user_subscription.id)

        except UserSubscription.DoesNotExist:
            print(f"Webhook Warning: Received customer.subscription.deleted for non-existent UserSubscription with Stripe sub ID: {stripe_subscription_id}")
        except Exception as e:
            print(f"Webhook Error: Failed to process customer.subscription.deleted for Stripe sub ID {stripe_subscription_id}. Error: {e}")

        return HttpResponse(status=200)
    
    else: # event['type'] != 'checkout.session.completed'
        print(f"Unhandled event type: {event['type']}")
        return HttpResponse(status=200)