# store/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import JsonResponse # Для AJAX ответов
from django.views.decorators.csrf import ensure_csrf_cookie # Импортируем декоратор
from .models import Product, Order, Category # Импортируем модели Product и Order
from .cart import Cart # Импортируем наш класс Cart
from decimal import Decimal
from django.contrib.auth import login # Функция для автоматического входа пользователя
from .forms import UserRegistrationForm # Импортируем нашу форму
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q

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

    context = {
        'orders': orders
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


def cart_detail(request):
    """
    Представление для отображения страницы корзины.
    """
    cart = Cart(request)
    # Передаем объект cart в шаблон. Шаблон сможет итерировать по нему.
    return render(request, 'store/cart_detail.html', {'cart': cart})