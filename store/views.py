# store/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import JsonResponse # Для AJAX ответов
from django.views.decorators.csrf import ensure_csrf_cookie # Импортируем декоратор
from .models import Product, Order, Category, Profile, SubscriptionBoxType, UserSubscription # Импортируем модели Product и Order
from .cart import Cart # Импортируем наш класс Cart
from decimal import Decimal
from django.contrib.auth import login # Функция для автоматического входа пользователя
from .forms import UserRegistrationForm, ProfileUpdateForm, SubscriptionChoiceForm # Импортируем нашу форму
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from blog.models import Post
from django.contrib import messages
import stripe
from django.urls import reverse, reverse_lazy
# from django.conf import settings # F401 unused import




@ensure_csrf_cookie
def product_list(request, category_slug=None):
    categories = Category.objects.all()
    products_list = Product.objects.filter(available=True).select_related('category')
    current_category = None
    query = None # Инициализируем переменную для запроса

    # --- Фильтрация по категории (как и раньше) ---
    if category_slug:
        current_category = get_object_or_404(Category, slug=category_slug)
        products_list = products_list.filter(category=current_category)

    # --- НОВАЯ ЛОГИКА: Фильтрация по поисковому запросу ---
    query = request.GET.get('query') # Получаем параметр 'query' из GET-запроса
    if query:
        # Если query не пустой, фильтруем queryset
        # Ищем совпадения (без учета регистра) в названии ИЛИ описании
        products_list = products_list.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    # --- КОНЕЦ ЛОГИКИ ПОИСКА ---

    # --- Пагинация (как и раньше) ---
    paginator = Paginator(products_list, 12)
    page_number = request.GET.get('page', 1)
    try:
        products = paginator.page(page_number)
    except PageNotAnInteger:
        products = paginator.page(1)
    except EmptyPage:
        products = paginator.page(paginator.num_pages)

    context = {
        'products': products,
        'categories': categories,
        'current_category': current_category,
        'query': query, # Передаем запрос в контекст (для отображения и пагинации)
    }
    return render(request, 'store/product_list.html', context)

@ensure_csrf_cookie
def product_detail(request, product_slug): # Принимаем product_slug вместо product_id
    """
    Представление для отображения страницы одного товара.
    Использует слаг для поиска товара.
    """
    # Ищем товар по слагу и доступности
    product = get_object_or_404(Product,
                                slug=product_slug, # Ищем по slug
                                available=True)
    context = {
        'product': product,
    }
    return render(request, 'store/product_detail.html', context)

def register(request):
    """Представление для регистрации нового пользователя."""
    if request.method == 'POST':
        # Если форма отправлена (метод POST)
        user_form = UserRegistrationForm(request.POST)
        if user_form.is_valid():
            # Создаем нового пользователя, но пока не сохраняем в базу данных
            new_user = user_form.save(commit=False)
            # Устанавливаем выбранный пароль
            # Метод set_password хэширует пароль перед сохранением
            new_user.set_password(user_form.cleaned_data['password2'])
            # Сохраняем пользователя в базе данных
            new_user.save()
            # Автоматически входим под новым пользователем
            login(request, new_user)
            # Перенаправляем на главную страницу после успешной регистрации и входа
            return redirect('/') # Или на страницу 'регистрация успешна'
        # Если форма невалидна, она будет отображена снова с ошибками
    else:
        # Если это GET запрос (просто открыли страницу) - создаем пустую форму
        user_form = UserRegistrationForm()

    # Рендерим шаблон, передавая ему форму
    return render(request, 'registration/register.html', {'user_form': user_form})

@login_required # Этот декоратор требует, чтобы пользователь был залогинен
def order_history(request):
    """Отображает историю заказов текущего пользователя."""
    # Получаем все заказы для текущего пользователя (request.user)
    # Сортируем по дате создания - сначала новые
    # prefetch_related('items__product') - оптимизация: заранее подгружает связанные
    # OrderItem и связанные с ними Product одним-двумя запросами, вместо
    # множества запросов внутри цикла в шаблоне.
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product').order_by('-created_at')
    user_subscriptions = UserSubscription.objects.filter(user=request.user).select_related('box_type').order_by('-start_date')
    context = {
        'orders': orders,
        'user_subscriptions': user_subscriptions,
        'page_title': 'Historia Zamówień i Subskrypcji'
    }
    return render(request, 'store/order_history.html', context)


@require_POST
def cart_add(request, product_id):
    """
    Представление для добавления товара в корзину или обновления количества.
    Ожидает AJAX запрос. Возвращает расширенный JSON ответ.
    """
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id) # Разрешаем добавлять/обновлять даже если available=False (если он уже в корзине)

    try:
        quantity = int(request.POST.get('quantity', 1))
        update = request.POST.get('update', 'false').lower() == 'true'

        if quantity < 0:
            raise ValueError("Quantity cannot be negative")

        # Сохраняем количество ДО операции, чтобы проверить, было ли оно скорректировано
        original_quantity_in_cart = cart.cart.get(str(product.id), {}).get('quantity', 0)

        cart.add(product=product, quantity=quantity, update_quantity=update)

        # Получаем обновленное состояние элемента из корзины ПОСЛЕ операции add
        updated_item_data = cart.cart.get(str(product.id))
        item_removed = updated_item_data is None
        final_quantity = 0 if item_removed else updated_item_data['quantity']
        item_total_price = "0.00" # По умолчанию, если товар удален

        quantity_adjusted = False
        adjusted_quantity = final_quantity

        if not item_removed:
            item_total_price = str(Decimal(updated_item_data['price']) * final_quantity)
            # Проверяем, было ли количество скорректировано из-за остатков
            # (если мы обновляли и итоговое количество меньше запрошенного, но > 0 ИЛИ если добавляли и итоговое кол-во не равно предыдущему + запрошенному)
            if update and final_quantity < quantity and final_quantity > 0:
                 quantity_adjusted = True
            elif not update and final_quantity != original_quantity_in_cart + quantity and final_quantity > 0:
                 # Случай, когда при добавлении уперлись в сток
                 quantity_adjusted = True


        response_data = {
            'status': 'ok',
            'cart_total_items': len(cart),
            'cart_total_price': str(cart.get_total_price()), # Конвертируем Decimal в строку для JSON
            'item_removed': item_removed, # Флаг, был ли товар удален (кол-во <= 0)
            'quantity_adjusted': quantity_adjusted, # Флаг, было ли кол-во скорректировано
            'adjusted_quantity': adjusted_quantity, # Итоговое количество в корзине
            'product_name': product.name, # Имя товара для сообщений
            'item_total_price': item_total_price # Общая цена для этой позиции
        }
        return JsonResponse(response_data)

    except Product.DoesNotExist:
         return JsonResponse({'status': 'error', 'error': 'Товар не найден'}, status=404)
    except ValueError as e:
         return JsonResponse({'status': 'error', 'error': f'Некорректное значение: {e}'}, status=400)
    except Exception as e:
         # Логирование ошибки здесь было бы полезно
         print(f"Error in cart_add: {e}") # Просто выводим в консоль для отладки
         return JsonResponse({'status': 'error', 'error': 'Внутренняя ошибка сервера'}, status=500)


@require_POST # Разрешаем только POST запросы
def cart_remove(request, product_id):
    """
    Представление для удаления товара из корзины.
    Ожидает AJAX запрос.
    """
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    cart.remove(product)

    # Возвращаем JSON ответ для AJAX
    # Можно добавить больше данных, если нужно обновить страницу динамически
    return JsonResponse({
        'status': 'ok',
        'cart_total_items': len(cart),
        'cart_total_price': cart.get_total_price() # Общая стоимость для обновления
    })

@ensure_csrf_cookie
def cart_detail(request):
    """
    Представление для отображения страницы корзины.
    """
    cart = Cart(request)
    # Передаем объект cart в шаблон. Шаблон сможет итерировать по нему.
    return render(request, 'store/cart_detail.html', {'cart': cart})

@ensure_csrf_cookie
def homepage(request):
    # Получаем несколько популярных/новых товаров для отображения (пример)
    featured_products = Product.objects.filter(available=True).select_related('category').order_by('-created_at')[:4] # Последние 4 товара

    # Получаем несколько последних постов из блога (пример)
    latest_posts = Post.objects.filter(status='published').select_related('author').order_by('-published_at')[:3] # Последние 3 опубликованных поста

    # Можно также получить категории для отображения
    categories = Category.objects.all()[:4] # Первые 4 категории

    context = {
        'featured_products': featured_products,
        'latest_posts': latest_posts,
        'categories': categories,
        'page_title': 'Witamy w EcoMarket!' # Для <title> тега
    }
    return render(request, 'store/homepage.html', context)

@login_required # Этот view доступен только залогиненным пользователям
def profile_update(request):
    # Получаем или создаем профиль для текущего пользователя
    # (Сигнал уже должен был создать профиль при регистрации, но на всякий случай)
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # Если форма отправлена
        # Мы передаем request.POST для текстовых данных и request.FILES для файлов (аватар)
        # instance=profile нужен, чтобы форма знала, какой объект Profile мы обновляем
        form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save() # Сохраняем изменения в профиле (включая новый аватар)
            messages.success(request, 'Twój profil został pomyślnie zaktualizowany!')
            return redirect('store:profile_update') # Перенаправляем обратно на эту же страницу (или другую)
        else:
            messages.error(request, 'Popraw błędy w formularzu.')
    else:
        # Если это GET-запрос, просто отображаем форму с текущими данными профиля
        form = ProfileUpdateForm(instance=profile)

    context = {
        'form': form,
        'profile': profile, # Передаем профиль для отображения текущего аватара
        'page_title': 'Edytuj Profil'
    }
    return render(request, 'store/profile_update.html', context)

@login_required
def process_subscription_checkout(request, box_type_id):
    try:
        selected_box = SubscriptionBoxType.objects.get(id=box_type_id, is_active=True)
    except SubscriptionBoxType.DoesNotExist:
        messages.error(request, "Wybrany typ boxa jest niedostępny.")
        return redirect('store:subscription_box_list')
    
    existing_active_subscriptions = UserSubscription.objects.filter(
        user=request.user,
        box_type=selected_box,
        status__in=['active', 'trialing', 'past_due']
    ).exists()

    if existing_active_subscriptions:
        messages.warning(request, f"Posiadasz już aktywną subskrypcję na '{selected_box.name}'. Możesz nią zarządzać w historii zamówień.")
        # Перенаправляем пользователя на страницу истории заказов/подписок
        return redirect('store:order_history')
    
    if not selected_box.stripe_price_id:
        messages.error(request, "Dla tego boxa nie skonfigurowano planu płatności. Prosimy o kontakt.")
        return redirect('store:subscription_box_list')

    success_url = request.build_absolute_uri(reverse('store:subscription_success')) # Нужен новый URL для успеха подписки
    cancel_url = request.build_absolute_uri(reverse('store:subscription_canceled')) # Нужен новый URL для отмены

    # Получаем или создаем Stripe Customer ID для пользователя
    # Это важно, чтобы все подписки пользователя были привязаны к одному клиенту в Stripe
    profile, _ = Profile.objects.get_or_create(user=request.user)
    stripe_customer_id = profile.stripe_customer_id

    checkout_session_params = {
        'mode': 'subscription',
        'payment_method_types': ['card'], # Добавь p24 или другие нужные методы
        'line_items': [{
            'price': selected_box.stripe_price_id,
            'quantity': 1,
        }],
        'success_url': success_url,
        'cancel_url': cancel_url,
        'metadata': {
            'django_user_id': str(request.user.id),
            'subscription_box_type_id': str(selected_box.id)
        },
        'subscription_data': {
            'metadata': {
                'django_user_id': str(request.user.id),
                'subscription_box_type_id': str(selected_box.id)
            }
        }
    }

    if stripe_customer_id:
        checkout_session_params['customer'] = stripe_customer_id
    else:
        checkout_session_params['customer_email'] = request.user.email
        # try:
        #     customer = stripe.Customer.create(email=request.user.email, name=request.user.get_full_name())
        #     profile.stripe_customer_id = customer.id
        #     profile.save()
        #     checkout_session_params['customer'] = customer.id
        # except stripe.error.StripeError as e:
        #     messages.error(request, f"Błąd przy tworzeniu klienta płatności: {e}")
        #     return redirect('store:subscription_box_list')


    try:
        session = stripe.checkout.Session.create(**checkout_session_params)
        return redirect(session.url, code=303)
    except stripe.error.StripeError as e:
        messages.error(request, f"Błąd systemu płatności przy tworzeniu sesji subskrypcji: {e}")
        return redirect('store:subscription_box_list')
    except Exception as e:
        messages.error(request, f"Wystąpił nieoczekiwany błąd: {e}")
        return redirect('store:subscription_box_list')
    


def subscription_box_list(request):
    active_boxes = SubscriptionBoxType.objects.filter(is_active=True)

    user_active_subscription_box_ids = []
    if request.user.is_authenticated:
        user_active_subscription_box_ids = list(UserSubscription.objects.filter(
            user=request.user,
            status__in=['active', 'trialing', 'past_due']
        ).values_list('box_type_id', flat=True))

    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.info(request, "Musisz być zalogowany, aby zasubskrybować box.")
            return redirect(reverse_lazy('login') + f"?next={request.path}")

        form = SubscriptionChoiceForm(request.POST)
        if form.is_valid():
            selected_box_type = form.cleaned_data['box_type']
            return redirect('store:process_subscription_checkout', box_type_id=selected_box_type.id)
        else:
            messages.error(request, "Proszę wybrać poprawny box.")
    else:
        form = SubscriptionChoiceForm()

    context = {
        'subscription_boxes': active_boxes,
        'form': form,
        'page_title': 'Wybierz Swój Eko Box Subskrypcyjny',
        'user_active_subscription_box_ids': user_active_subscription_box_ids,
    }
    return render(request, 'store/subscription_box_list.html', context)


def subscription_box_detail(request, slug):
    """
    Представление для отображения детальной страницы типа подписочного бокса.
    """
    box_type = get_object_or_404(SubscriptionBoxType, slug=slug, is_active=True)
    context = {
        'box_type': box_type,
        'page_title': box_type.name # Для тега <title>
    }
    return render(request, 'store/subscription_box_detail.html', context)
    

def subscription_success(request):
    # Здесь можно будет добавить логику очистки корзины или показа деталей подписки
    messages.success(request, "Dziękujemy za subskrypcję! Oczekuj na potwierdzenie.")
    return render(request, 'store/subscription_feedback.html', {'feedback_title': "Subskrypcja Udana!", 'feedback_message': "Twoja subskrypcja została pomyślnie zainicjowana. Szczegóły otrzymasz wkrótce."})

def subscription_canceled(request):
    messages.warning(request, "Proces subskrypcji został anulowany.")
    return render(request, 'store/subscription_feedback.html', {'feedback_title': "Subskrypcja Anulowana", 'feedback_message': "Możesz spróbować ponownie w dowolnym momencie."})



@login_required
def cancel_subscription(request, subscription_id):
    """
    Обрабатывает запрос пользователя на отмену подписки (в конце периода).
    """
    # Находим локальную запись о подписке
    user_subscription = get_object_or_404(UserSubscription, id=subscription_id, user=request.user)

    if not user_subscription.stripe_subscription_id:
        messages.error(request, "Для этой подписки отсутствует ID в системе Stripe. Обратитесь в поддержку.")
        return redirect('store:order_history')

    if user_subscription.status == 'canceled' or user_subscription.cancel_at_period_end:
        messages.info(request, f"Подписка на '{user_subscription.box_type.name}' уже отменена или запланирована к отмене.")
        return redirect('store:order_history')

    if request.method == 'POST':
        try:
            # Устанавливаем флаг отмены в конце периода в Stripe
            # stripe.api_key = settings.STRIPE_SECRET_KEY # Уже должно быть установлено глобально при импорте stripe
            stripe.Subscription.modify(
                user_subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )

            # Обновляем локальную запись (флаг cancel_at_period_end обновится через вебхук customer.subscription.updated)
            # Но можно и сразу установить для немедленной обратной связи в UI,
            # хотя вебхук должен быть основным источником правды.
            # user_subscription.cancel_at_period_end = True
            # user_subscription.save(update_fields=['cancel_at_period_end'])

            messages.success(request, f"Ваша подписка на '{user_subscription.box_type.name}' будет отменена в конце текущего расчетного периода.")
            print(f"User {request.user.id} requested to cancel Stripe subscription {user_subscription.stripe_subscription_id} at period end.")

        except stripe.error.StripeError as e:
            messages.error(request, f"Произошла ошибка при отмене подписки в Stripe: {e}")
            print(f"StripeError cancelling subscription {user_subscription.stripe_subscription_id}: {e}")
        except Exception as e:
            messages.error(request, f"Произошла непредвиденная ошибка: {e}")
            print(f"Error cancelling subscription {user_subscription.stripe_subscription_id}: {e}")

        return redirect('store:order_history')
    else:
        # Для GET-запроса можно показать страницу подтверждения отмены,
        # но для простоты мы будем использовать POST-запрос напрямую с кнопки.
        # Если нужна страница подтверждения, здесь нужно будет рендерить шаблон.
        messages.warning(request, "Для отмены подписки используйте соответствующую кнопку.")
        return redirect('store:order_history')