# payments/views.py
from django.db.models import F # <--- Импорт для атомарных обновлений
from django.db import transaction 
import stripe # Импортируем библиотеку Stripe
from decimal import Decimal # Для работы с ценами
from django.conf import settings # Для доступа к ключам API и другим настройкам
from django.shortcuts import render, redirect, reverse, get_object_or_404
from store.models import Product, Order, OrderItem # Импортируем модель Order (пока не используем, но понадобится)
from store.cart import Cart # Импортируем нашу корзину
from django.contrib import messages
from django.http import HttpResponse # Для отправки ответа Stripe
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from store.forms import OrderCreateForm
from .email import send_order_confirmation_email

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
         # Возвращаем 500, т.к. это ошибка конфигурации сервера
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
        print(f"Processing checkout.session.completed for session: {session.id}")

        if session.payment_status == "paid":
            # --- НАЧАЛО ОБРАБОТКИ ОПЛАЧЕННОЙ СЕССИИ ---
            try:
                # Проверяем дубликат
                if Order.objects.filter(stripe_id=session.id).exists():
                    print(f"Order for session {session.id} already exists.")
                    return HttpResponse(status=200)

                metadata = session.get('metadata', {})
                user_id_from_metadata = metadata.get('user_id')
                first_name = metadata.get('first_name', '')
                last_name = metadata.get('last_name', '')
                # Email берем из customer_details (Stripe его часто сам получает) или из метаданных
                email = session.customer_details.email if session.customer_details else metadata.get('email', '')
                address_line_1 = metadata.get('address_line_1', '')
                address_line_2 = metadata.get('address_line_2', '')
                postal_code = metadata.get('postal_code', '')
                city = metadata.get('city', '')
                country = metadata.get('country', '')

                # Получаем пользователя
                User = get_user_model()
                user = None
                if user_id_from_metadata:
                        # Если user_id_from_metadata не пустой, не состоит только из пробелов и не строка "None"
                    try:
                        user = User.objects.get(id=int(user_id_from_metadata))
                        print(f"User {user} found for order.")
                    except (User.DoesNotExist, ValueError, TypeError):
                        print(f"Webhook Warning: User with id='{user_id_from_metadata}' (from metadata) not found or invalid for session {session.id}.")
                        user = None # Если не нашли или ID некорректный, заказ будет анонимным
                else:
                    print(f"Webhook Info: No valid user_id in metadata for session {session.id}. Order will be anonymous.")
                    user = None

                # Запрашиваем line_items
                print(f"Fetching line items for session {session.id}...")
                try:
                    line_items_response = stripe.checkout.Session.list_line_items(
                        session.id, limit=50, expand=['data.price.product']
                    )
                    if not line_items_response or not line_items_response.data:
                         print(f"Webhook Error: Could not retrieve line items for session {session.id}")
                         return HttpResponse(status=500) # Ошибка сервера, не можем создать заказ
                    print(f"Line items fetched successfully: {len(line_items_response.data)} items.")
                except stripe.error.StripeError as e:
                    print(f"Webhook Error: Stripe API error fetching line items for session {session.id}: {e}")
                    return HttpResponse(status=500) # Ошибка сервера

                # Создаем заказ и элементы в транзакции
                with transaction.atomic():
                    order = Order.objects.create(
                        user=user,
                        paid=True,
                        stripe_id=session.id,
                        first_name=metadata.get('first_name', ''), # Используем get для безопасности
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
                        # ... (логика внутри цикла как была, с try/except Product.DoesNotExist) ...
                         try:
                            price_info = item_data.get('price', {})
                            product_info = price_info.get('product', {})
                            metadata = product_info.get('metadata', {})
                            product_db_id = metadata.get('product_db_id')
                            if not product_db_id: raise ValueError("Missing product ID in metadata")

                            product = Product.objects.get(id=product_db_id)
                            quantity = item_data.get('quantity', 0)
                            unit_amount = price_info.get('unit_amount', 0)
                            price_paid = Decimal(unit_amount) / 100

                            items_to_create.append(OrderItem(
                                order=order, product=product, price=price_paid, quantity=quantity
                            ))
                            products_stock_update[product.id] = products_stock_update.get(product.id, 0) + quantity
                         except Product.DoesNotExist:
                            print(f"Webhook Error: Product with id={product_db_id} not found (session {session.id}). Order creation failed.")
                            raise ValueError(f"Product {product_db_id} not found") # Это откатит транзакцию
                         except Exception as e:
                            print(f"Webhook Error: Problem processing line item: {e}")
                            raise # Откатываем транзакцию

                    if items_to_create: OrderItem.objects.bulk_create(items_to_create)
                    for prod_id, qty_decrement in products_stock_update.items():
                        Product.objects.filter(id=prod_id).update(stock=F('stock') - qty_decrement)

                # Если транзакция прошла успешно:
                print(f"Order {order.id} successfully created from webhook for session {session.id}")
                # --- ДОБАВЛЯЕМ ЯВНЫЙ RETURN ПОСЛЕ УСПЕХА ---
                print(f"Attempting to send confirmation email for Order #{order.id}...")
                send_order_confirmation_email(order)
                return HttpResponse(status=200)
                # ------------------------------------------

            except Exception as e:
                # Ошибка во время обработки (получения пользователя, запроса line_items, транзакции)
                print(f"Webhook Error: Failed to process PAID session {session.id}. Error: {e}")
                return HttpResponse(status=500) # Ошибка сервера
            # --- КОНЕЦ ОБРАБОТКИ ОПЛАЧЕННОЙ СЕССИИ ---

        else: # Если payment_status != "paid"
             print(f"Payment status for session {session.id} is '{session.payment_status}', not creating order.")
             return HttpResponse(status=200) # OK, обработали (проигнорировали)

    else: # Если event['type'] НЕ 'checkout.session.completed'
        print(f"Unhandled event type: {event['type']}")
        return HttpResponse(status=200) # OK, обработали (проигнорировали)