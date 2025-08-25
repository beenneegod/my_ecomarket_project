# store/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import JsonResponse # Для AJAX ответов
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from .models import Product, Order, Category, Profile, SubscriptionBoxType, UserSubscription, Coupon, UserCoupon, ProductRating # Импортируем UserCoupon
from .cart import Cart
from decimal import Decimal
from django.contrib.auth import login # Функция для автоматического входа пользователя
from .forms import UserRegistrationForm, ProfileUpdateForm, SubscriptionChoiceForm, CouponApplyForm, UserCouponChoiceForm, CartAddProductForm, ContactForm # Добавлен CartAddProductForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count
from django.db.models import Avg
from blog.models import Post
from django.contrib import messages
import stripe
from django.urls import reverse, reverse_lazy
from django.conf import settings
from django.utils import timezone
import logging
logger = logging.getLogger(__name__)
from django.core.mail import send_mail
import requests




@ensure_csrf_cookie
def product_list(request, category_slug=None):
    categories = Category.objects.all()
    products_list = Product.objects.filter(available=True)
    current_category = None
    query = None # Инициализируем переменную для запроса

    # --- Фильтрация по категории (как и раньше) ---
    if category_slug:
        current_category = get_object_or_404(Category, slug=category_slug)
        products_list = products_list.filter(category=current_category)

    # --- Фильтрация по поисковому запросу ---
    query = request.GET.get('query') # Получаем параметр 'query' из GET-запроса
    if query:
        # Если query не пустой, фильтруем queryset
        # Ищем совпадения (без учета регистра) в названии ИЛИ описании
        products_list = products_list.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    # --- Цена: min/max ---
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    try:
        min_val = Decimal(min_price) if min_price not in (None, "") else None
    except Exception:
        min_val = None
    try:
        max_val = Decimal(max_price) if max_price not in (None, "") else None
    except Exception:
        max_val = None
    # Если оба заданы и перепутаны — поменяем местами
    if min_val is not None and max_val is not None and min_val > max_val:
        min_val, max_val = max_val, min_val
    if min_val is not None:
        products_list = products_list.filter(price__gte=min_val)
    if max_val is not None:
        products_list = products_list.filter(price__lte=max_val)

    # --- Аггрегаты рейтинга (до сортировки/пагинации) ---
    products_list = products_list.annotate(
        avg_rating=Avg('ratings__value'),
        rating_count=Count('ratings')
    )

    # --- Фильтр по минимальному рейтингу ---
    min_rating_param = request.GET.get('min_rating')
    try:
        if min_rating_param not in (None, ''):
            mr = float(min_rating_param)
            products_list = products_list.filter(avg_rating__gte=mr)
    except Exception:
        pass

    # --- Сортировка ---
    sort = request.GET.get('sort') or 'new'
    if sort == 'price_asc':
        products_list = products_list.order_by('price', '-created_at')
    elif sort == 'price_desc':
        products_list = products_list.order_by('-price', '-created_at')
    elif sort == 'popular':
        products_list = products_list.annotate(order_count=Count('order_items')).order_by('-order_count', '-created_at')
    elif sort == 'rating_desc':
        # сначала по средней оценке, затем по количеству голосов, затем по новизне
        products_list = products_list.order_by('-avg_rating', '-rating_count', '-created_at')
    elif sort == 'rating_asc':
        products_list = products_list.order_by('avg_rating', '-rating_count', '-created_at')
    else:  # 'new' по умолчанию
        products_list = products_list.order_by('-created_at')

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
        'sort': sort,
        'min_price': min_price,
        'max_price': max_price,
        'min_rating': request.GET.get('min_rating') or '',
        }
    return render(request, 'store/product_list.html', context)

@ensure_csrf_cookie
def product_detail(request, product_slug):
    product = get_object_or_404(Product, slug=product_slug, available=True)
    # Fetch rating aggregates
    agg = product.ratings.aggregate(avg=Avg('value'), cnt=Count('id'))
    avg_rating = agg.get('avg') or 0
    rating_count = agg.get('cnt') or 0
    user_rating_value = None
    if request.user.is_authenticated:
        try:
            ur = ProductRating.objects.get(product=product, user=request.user)
            user_rating_value = ur.value
        except ProductRating.DoesNotExist:
            user_rating_value = None
    related_products = []
    if product.category: # Check if the product has a category
        related_products = Product.objects.filter(
            category=product.category,
            available=True
        ).exclude(id=product.id)[:4] # Get up to 4 related products

    context = {
        'product': product,
        'related_products': related_products, # Add to context
        'product_avg_rating': avg_rating,
        'product_rating_count': rating_count,
        'user_rating_value': user_rating_value,
    }
    return render(request, 'store/product_detail.html', context)

@login_required
@require_POST
def rate_product(request, product_id: int):
    """Create/update a user's 1-5 star rating for a product; returns JSON with new average and count."""
    try:
        product = Product.objects.get(id=product_id, available=True)
    except Product.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Produkt nie został znaleziony'}, status=404)

    try:
        data = request.POST
        v = int(data.get('value') or 0)
    except Exception:
        v = 0
    if v not in (1,2,3,4,5):
        return JsonResponse({'ok': False, 'error': 'Ocena musi być w zakresie 1-5.'}, status=400)

    obj, _ = ProductRating.objects.update_or_create(product=product, user=request.user, defaults={'value': v})
    agg = product.ratings.aggregate(avg=Avg('value'), cnt=Count('id'))
    avg = agg.get('avg') or 0
    cnt = agg.get('cnt') or 0
    return JsonResponse({'ok': True, 'average': round(avg, 2), 'count': cnt, 'your_value': v})

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


@ensure_csrf_cookie  # This ensures CSRF cookie is set
def cart_add(request, product_id):
    """
    Представление для добавления товара в корзину или обновления количества.
    Ожидает AJAX запрос. Возвращает расширенный JSON ответ.
    """
    cart = Cart(request)

    # For AJAX requests, we'll be more lenient with CSRF
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            product = Product.objects.get(id=product_id, available=True)
        except Product.DoesNotExist:
            return JsonResponse({'status': 'error', 'error': 'Produkt nie został znaleziony'}, status=404)

        # Extract quantity directly from POST data if form validation fails
        try:
            quantity = int(request.POST.get('quantity', 1))
            update = request.POST.get('update', 'false').lower() in ('true', '1', 't')
            
            # Basic validation: allow 0 only when updating (treats as item removal)
            if quantity < 0 or (not update and quantity == 0):
                return JsonResponse({'status': 'error', 'error': 'Ilość musi być większa od 0'}, status=400)
                
            # Preserve the form for cleaner code path when it works
            # If quantity==0 and update==True, skip form (its min_value=1)
            if quantity == 0 and update:
                pass
            else:
                form = CartAddProductForm(request.POST)
                if not form.is_valid():
                    # Fall back to direct POST data extraction
                    print(f"Form invalid, using direct POST data. Errors: {form.errors}")
                else:
                    # Use form data when valid
                    quantity = form.cleaned_data['quantity']
                    update = form.cleaned_data['update']
            
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
                'cart_total_price_after_discount': str(cart.get_total_price_after_discount()),
                'cart_discount_amount': str(cart.get_discount_amount()),
                'item_removed': item_removed, # Флаг, был ли товар удален (кол-во <= 0)
                'quantity_adjusted': quantity_adjusted, # Флаг, было ли кол-во скорректировано
                'adjusted_quantity': adjusted_quantity, # Итоговое количество в корзине
                'product_name': product.name, # Имя товара для сообщений
                'item_total_price': item_total_price # Общая цена для этой позиции
            }
            return JsonResponse(response_data)
        except ValueError:
            return JsonResponse({'status': 'error', 'error': 'Nieznany błąd'}, status=400)
        except Exception as e:
            print(f"Unexpected error in cart_add: {str(e)}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

    # Regular non-AJAX request handling
    product = get_object_or_404(Product, id=product_id) # Разрешаем добавлять/обновлять даже если available=False (если он уже в корзине)
    try:
        quantity = int(request.POST.get('quantity', 1))
        update = request.POST.get('update', 'false').lower() == 'true'

        if quantity < 0:
            messages.error(request, "Ilość nie może być ujemna")
        else:
            cart.add(product=product, quantity=quantity, update_quantity=update)
            messages.success(request, f"Produkt '{product.name}' dodano do koszyka")
    except (ValueError, TypeError):
        messages.error(request, "Nieprawidłowa ilość produktu")

    return redirect('store:cart_detail')


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
    'cart_total_price': str(cart.get_total_price()),
    'cart_total_price_after_discount': str(cart.get_total_price_after_discount()),
    'cart_discount_amount': str(cart.get_discount_amount()),
    'cart_empty': len(cart) == 0,
    })

@ensure_csrf_cookie
def cart_detail(request):
    """
    Представление для отображения страницы корзины.
    """
    cart = Cart(request)
    coupon_apply_form = CouponApplyForm()
    user_coupon_choice_form = None
    available_user_coupons = None

    if request.user.is_authenticated:
        now = timezone.now()
        available_user_coupons = UserCoupon.objects.filter(
            user=request.user,
            is_used=False,
            coupon__active=True,
            coupon__valid_from__lte=now,
            coupon__valid_to__gte=now
        ).select_related('coupon')
        
        if available_user_coupons.exists():
            user_coupon_choice_form = UserCouponChoiceForm(user=request.user) # Передаем пользователя в форму

    context = {
        'cart': cart,
        'coupon_apply_form': coupon_apply_form,
        'user_coupon_choice_form': user_coupon_choice_form,
        'available_user_coupons': available_user_coupons # Можно использовать для прямого отображения, если форма не нужна
    }
    return render(request, 'store/cart_detail.html', context)

@ensure_csrf_cookie
def homepage(request):
    # Получаем несколько популярных/новых товаров для отображения (пример)
    featured_products = Product.objects.filter(available=True).order_by('-created_at')[:4] # Последние 4 товара

    # Получаем несколько последних постов из блога (пример)
    latest_posts = Post.objects.filter(status='published').order_by('-published_at')[:3] # Последние 3 опубликованных поста

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
            try:
                # Сохраняем изменения в профиле (включая новый аватар)
                obj = form.save()
                # Доп. защита: если пришёл флаг avatar_clear, а форма/виджет могли его игнорировать — почистим сервером
                if request.POST.get('avatar_clear') in ('1', 'true', 'on'):
                    try:
                        if obj.avatar:
                            obj.avatar.delete(save=False)
                            obj.avatar = None
                            obj.save(update_fields=['avatar'])
                    except Exception:
                        pass
                messages.success(request, 'Twój profil został pomyślnie zaktualizowany!')
                return redirect('store:profile_update') # Перенаправляем обратно на эту же страницу (или другую)
            except Exception as e:
                try:
                    uploaded_present = bool(request.FILES.get('avatar'))
                except Exception:
                    uploaded_present = None
                try:
                    storage_name = type(profile.avatar.storage).__name__ if profile and profile.avatar else None
                except Exception:
                    storage_name = None
                logger.exception(
                    "Profile update failed",
                    extra={
                        'user_id': getattr(request.user, 'id', None),
                        'uploaded_present': uploaded_present,
                        'storage': storage_name,
                        'avatar_clear': request.POST.get('avatar_clear'),
                    }
                )
                messages.error(request, 'Nie udało się zapisać zmian profilu. Spróbuj ponownie lub wybierz inny plik.')
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
        messages.error(request, "Dla tej subskrypcji brakuje identyfikatora w systemie Stripe. Skontaktuj się z pomocą techniczną.")
        return redirect('store:order_history')

    if user_subscription.status == 'canceled' or user_subscription.cancel_at_period_end:
        messages.info(request, f"Subskrypcja na '{user_subscription.box_type.name}' jest już anulowana lub zaplanowana do anulowania.")
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

            messages.success(request, f"Twoja subskrypcja na '{user_subscription.box_type.name}' zostanie anulowana na koniec bieżącego okresu rozliczeniowego.")
            print(f"User {request.user.id} requested to cancel Stripe subscription {user_subscription.stripe_subscription_id} at period end.")

        except stripe.error.StripeError as e:
            messages.error(request, f"Wystąpił błąd podczas anulowania subskrypcji w Stripe: {e}")
            print(f"StripeError cancelling subscription {user_subscription.stripe_subscription_id}: {e}")
        except Exception as e:
            messages.error(request, f"Wystąpił nieoczekiwany błąd: {e}")
            print(f"Error cancelling subscription {user_subscription.stripe_subscription_id}: {e}")

        return redirect('store:order_history')
    else:
        # Для GET-запроса можно показать страницу подтверждения отмены,
        # но для простоты мы будем использовать POST-запрос напрямую с кнопки.
        # Если нужна страница подтверждения, здесь нужно будет рендерить шаблон.
        messages.warning(request, "Aby anulować subskrypcję, użyj odpowiedniego przycisku.")
        return redirect('store:order_history')


@require_POST
def coupon_apply(request):
    now = timezone.now()
    cart = Cart(request)
    source_form = request.POST.get('source_form')
    applied_coupon = None

    if source_form == 'user_choice' and request.user.is_authenticated:
        form = UserCouponChoiceForm(request.POST, user=request.user) # Передаем user для валидации queryset
        if form.is_valid():
            user_coupon_instance = form.cleaned_data['user_coupon']
            # Дополнительная проверка, что купон действительно принадлежит пользователю и активен
            # (хотя форма должна была это сделать, но для безопасности)
            if user_coupon_instance.user == request.user and \
               user_coupon_instance.coupon.active and \
               not user_coupon_instance.is_used and \
               user_coupon_instance.coupon.valid_from <= now <= user_coupon_instance.coupon.valid_to:
                applied_coupon = user_coupon_instance.coupon
            else:
                messages.error(request, "Wybrany kupon jest nieprawidłowy lub już nieważny.")
        else:
            # Обычно ошибки формы обрабатываются в cart_detail при GET запросе,
            # но если пользователь как-то отправит невалидную форму напрямую:
            messages.error(request, "Wystąpił błąd przy wyborze kuponu. Spróbuj ponownie.")
            # Можно добавить логирование ошибок формы: e.g., logger.error(form.errors.as_json())

    elif source_form == 'manual_apply':
        form = CouponApplyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            try:
                coupon = Coupon.objects.get(
                    code__iexact=code,
                    active=True,
                    valid_from__lte=now,
                    valid_to__gte=now
                )
                applied_coupon = coupon
            except Coupon.DoesNotExist:
                messages.error(request, 'Ten kupon jest nieprawidłowy lub wygasł.')
        # Если форма невалидна, сообщение об ошибке не нужно, т.к. поле одно и оно required
        # или можно добавить messages.error(request, 'Proszę wprowadzić kod kuponu.') если поле пустое

    else:
        messages.error(request, "Nieprawidłowe żądanie zastosowania kuponu.")

    if applied_coupon:
        cart.set_coupon(applied_coupon)
        messages.success(request, f'Kupon "{applied_coupon.code}" został pomyślnie zastosowany.')

    # Support optional redirect back target
    next_url = request.POST.get('next')
    if next_url:
        try:
            from django.utils.http import url_has_allowed_host_and_scheme
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
        except Exception:
            pass
    return redirect('store:cart_detail')


@require_POST
def remove_coupon(request):
    """
    Удаляет купон из сессии (корзины).
    """
    cart = Cart(request)
    cart.clear_coupon()
    messages.info(request, "Kupon został usunięty z koszyka.")
    return redirect('store:cart_detail')


def cart_count(request):
    """
    Simple view to return the current cart count as JSON.
    Used for AJAX requests after iframe form submissions.
    """
    cart = Cart(request)
    return JsonResponse({
        'count': len(cart),
        'total': str(cart.get_total_price()),
    })


def contact(request):
    """Public contact page to reach the shop support."""
    initial = {}
    if request.user.is_authenticated:
        initial['email'] = getattr(request.user, 'email', '')
        initial['name'] = (request.user.get_full_name() or request.user.username or '').strip()
    if request.method == 'POST':
        form = ContactForm(request.POST, user=request.user)
        if form.is_valid():
            name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['message']
            token = form.cleaned_data.get('recaptcha_token')

            # Verify reCAPTCHA (skip in dev if not configured)
            recaptcha_ok = True
            secret = getattr(settings, 'RECAPTCHA_SECRET_KEY', '')
            if secret:
                recaptcha_ok = False
                try:
                    resp = requests.post(
                        'https://www.google.com/recaptcha/api/siteverify',
                        data={
                            'secret': secret,
                            'response': token,
                            'remoteip': request.META.get('REMOTE_ADDR')
                        },
                        timeout=10
                    )
                    data = resp.json()
                    if data.get('success'):
                        score = float(data.get('score', 0)) if 'score' in data else 1.0
                        recaptcha_ok = score >= getattr(settings, 'RECAPTCHA_MIN_SCORE', 0.5)
                except Exception as e:
                    logger.warning('reCAPTCHA verification failed: %s', e)
                    recaptcha_ok = False
            else:
                if not settings.DEBUG:
                    recaptcha_ok = True  # allow if keys missing but not to block prod unexpectedly

            if not recaptcha_ok:
                messages.error(request, 'Weryfikacja reCAPTCHA nie powiodła się. Spróbuj ponownie.')
                return render(request, 'store/contact.html', {'form': form, 'page_title': 'Kontakt z EcoMarket'})
            full_subject = f"[Kontakt] {subject}"
            body = (
                f"Imię i nazwisko: {name}\n"
                f"E-mail: {email}\n"
                f"Użytkownik: {request.user.id if request.user.is_authenticated else 'anonim'}\n\n"
                f"Wiadomość:\n{message}"
            )
            try:
                support_email = getattr(settings, 'SUPPORT_EMAIL', None) or getattr(settings, 'DEFAULT_FROM_EMAIL', None)
                if not support_email:
                    # fallback: print to logs when mail is not configured
                    logger.info("Contact message (mail disabled): %s\n%s", full_subject, body)
                else:
                    send_mail(
                        subject=full_subject,
                        message=body,
                        from_email=settings.DEFAULT_FROM_EMAIL or support_email,
                        recipient_list=[support_email],
                        fail_silently=False,
                        html_message=None,
                    )
                    # Autoresponder to the customer
                    try:
                        send_mail(
                            subject='Potwierdzenie kontaktu – EcoMarket',
                            message=(
                                'Dziękujemy za kontakt! Otrzymaliśmy Twoją wiadomość i odpowiemy tak szybko, jak to możliwe.\n\n'
                                f'Temat: {subject}\n'
                                f'Treść:\n{message}\n\n'
                                'Pozdrawiamy,\nZespół EcoMarket'
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL or support_email,
                            recipient_list=[email],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                messages.success(request, 'Dziękujemy za kontakt! Odpowiemy tak szybko, jak to możliwe.')
                return redirect('store:contact')
            except Exception as e:
                logger.exception("Contact form send failed: %s", e)
                messages.error(request, 'Nie udało się wysłać wiadomości. Spróbuj ponownie później lub napisz bezpośrednio e‑mail.')
    else:
        form = ContactForm(initial=initial, user=request.user)
    context = {
        'form': form,
        'page_title': 'Kontakt z EcoMarket',
    }
    return render(request, 'store/contact.html', context)