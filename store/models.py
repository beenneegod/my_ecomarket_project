# store/models.py

from django.db import models
from django.conf import settings # Для ссылки на модель пользователя
from django.urls import reverse
from django.utils.text import slugify

class Category(models.Model):
    """Модель категории товаров"""
    name = models.CharField(max_length=200, db_index=True, verbose_name="Название")
    # Slug - это часть URL, обычно формируется из названия (например, 'kukhonnaya-tekhnika')
    # unique=True гарантирует, что слаги не будут повторяться
    slug = models.SlugField(max_length=200, unique=True, verbose_name="URL slug")

    class Meta:
        ordering = ('name',)
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        """Возвращает URL для отображения товаров этой категории."""
        # 'store:product_list_by_category' - это имя URL, которое мы создадим позже
        return reverse('store:product_list_by_category', args=[self.slug])

class Product(models.Model):
    category = models.ForeignKey(Category,
                                 related_name='products', # Имя для обратной связи Category -> Product
                                 on_delete=models.SET_NULL, # При удалении категории, у товара поле category станет NULL
                                 null=True, # Разрешаем NULL в БД (товар может быть без категории)
                                 blank=True, # Разрешаем оставлять поле пустым в формах (админке)
                                 verbose_name="Kategoria")
    name = models.CharField(max_length=255, verbose_name="Nazwa")
    slug = models.SlugField(max_length=255,
                            unique=True,       # Слаги должны быть уникальными
                            db_index=True,     # Индекс для быстрого поиска по слагу
                            null=True,         # Временно разрешаем NULL (для существующих товаров)
                            blank=True,        # Временно разрешаем быть пустым в формах
                            verbose_name="URL slug")
    description = models.TextField(blank=True, verbose_name="Описание") # Описание может быть необязательным
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена") # Используем DecimalField для точности
    stock = models.PositiveIntegerField(default=0, verbose_name="Остаток на складе") # Количество не может быть отрицательным
    image = models.ImageField(upload_to='products/%Y/%m/%d/', blank=True, null=True, verbose_name="Изображение") # Картинка товара (необязательно)
    # upload_to создает подпапки по году/месяцу/дню для порядка
    available = models.BooleanField(default=True, verbose_name="Доступен") # Флаг доступности товара
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания") # Дата добавления (автоматически при создании)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления") # Дата последнего обновления (автоматически при сохранении)
    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ['name'] # Сортировка по умолчанию по названию

    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        """Возвращает канонический URL для страницы деталей товара."""
        return reverse('store:product_detail', args=[self.slug])
    
    def save(self, *args, **kwargs):
        if not self.slug and self.name: # Генерируем слаг, только если он не установлен и есть имя
            self.slug = slugify(self.name)
            # Начальная проверка на уникальность и добавление суффикса, если необходимо
            # Это базовая реализация, для высокой нагрузки может потребоваться более сложная логика
            original_slug = self.slug
            counter = 1
            # Проверяем, существует ли уже такой слаг (исключая текущий объект, если он уже сохранен)
            queryset = Product.objects.filter(slug=self.slug)
            if self.pk: # Если объект уже существует в БД
                queryset = queryset.exclude(pk=self.pk)

            while queryset.exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
                # Обновляем queryset для следующей проверки
                queryset = Product.objects.filter(slug=self.slug)
                if self.pk:
                    queryset = queryset.exclude(pk=self.pk)

        super().save(*args, **kwargs)

class Order(models.Model):
    """Модель заказа"""
    # Связь с пользователем. Используем settings.AUTH_USER_MODEL для гибкости.
    # null=True, blank=True позволят создавать заказы для неавторизованных пользователей (если понадобится)
    # on_delete=models.SET_NULL - если пользователь удален, заказ остается, но без пользователя
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders', verbose_name="Пользователь")
    # Дополнительные поля для адреса доставки и т.д. можно добавить сюда
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    last_name = models.CharField(max_length=100, verbose_name="Фамилия")
    email = models.EmailField(verbose_name="Email")
    address_line_1 = models.CharField(max_length=250, verbose_name="Адрес (улица, дом)")
    address_line_2 = models.CharField(max_length=250, blank=True, verbose_name="Адрес (кв., офис - необязательно)")
    postal_code = models.CharField(max_length=20, verbose_name="Почтовый индекс")
    city = models.CharField(max_length=100, verbose_name="Город")
    # Поле страны пока сделаем простым текстом, можно усложнить позже
    country = models.CharField(max_length=100, default="Польша", verbose_name="Страна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    paid = models.BooleanField(default=False, verbose_name="Оплачен") # Статус оплаты
    stripe_id = models.CharField(max_length=250, blank=True, verbose_name="ID транзакции Stripe") # Для хранения ID сессии/платежа Stripe

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ['-created_at'] # Сортировка по умолчанию - сначала новые

    def __str__(self):
        return f"Заказ №{self.id}"

    def get_total_cost(self):
        """Возвращает общую стоимость заказа"""
        return sum(item.get_cost() for item in self.items.all())

class OrderItem(models.Model):
    """Модель элемента заказа (конкретный товар в заказе)"""
    # Связь с заказом. related_name='items' позволяет обращаться к элементам заказа через order.items.all()
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE, verbose_name="Заказ")
    # Связь с товаром. related_name='order_items' - для обратного доступа (product.order_items.all())
    product = models.ForeignKey(Product, related_name='order_items', on_delete=models.PROTECT, verbose_name="Товар") # PROTECT - не даст удалить товар, если он есть в заказах
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена") # Цена товара НА МОМЕНТ покупки
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")

    class Meta:
        verbose_name = "Элемент заказа"
        verbose_name_plural = "Элементы заказа"
        # Уникальность пары заказ-товар, чтобы один товар не добавлялся дважды в один заказ как отдельный OrderItem
        # unique_together = ('order', 'product') # Раскомментируйте, если нужно строго это правило

    def __str__(self):
        return f"{self.quantity} x {self.product.name} в Заказе №{self.order.id}"

    def get_cost(self):
        """Возвращает стоимость данного элемента заказа (цена * количество)"""
        return self.price * self.quantity
    

class Profile(models.Model): # Без отступа в начале строки
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(blank=True, null=True, verbose_name="O sobie")
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Stripe Customer ID")
    class Meta:
        verbose_name = "Profil użytkownika"
        verbose_name_plural = "Profile użytkowników"

    def __str__(self):
        return f"Profil użytkownika {self.user.username}"

    @property
    def avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        else:
            from django.templatetags.static import static
            return static('img/default_avatar.png')
        


class SubscriptionBoxType(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nazwa Boxa Subskrypcyjnego")
    slug = models.SlugField(max_length=200, unique=True, verbose_name="URL slug")
    description = models.TextField(verbose_name="Opis")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cena za okres")
    # Частота подписки, например, 'weekly', 'monthly'
    # Можно использовать Choices для предопределенных вариантов
    BILLING_PERIOD_CHOICES = [
        ('week', 'Tygodniowo'),
        ('month', 'Miesięcznie'),
        # ('year', 'Rocznie'), # Если нужно
    ]
    billing_period = models.CharField(
        max_length=10,
        choices=BILLING_PERIOD_CHOICES,
        default='month',
        verbose_name="Okres rozliczeniowy"
    )
    image = models.ImageField(upload_to='subscription_boxes/', blank=True, null=True, verbose_name="Obrazek Boxa")
    is_active = models.BooleanField(default=True, verbose_name="Aktywny (dostępny do subskrypcji)")
    # Поле для ID тарифного плана в Stripe (Stripe Price ID)
    stripe_price_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Stripe Price ID")


    class Meta:
        verbose_name = "Typ Boxa Subskrypcyjnego"
        verbose_name_plural = "Typy Boxów Subskrypcyjnych"
        ordering = ['price']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        # Позже создадим URL для детальной страницы типа бокса
        return reverse('store:subscription_box_detail', args=[self.slug])


class UserSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    box_type = models.ForeignKey(SubscriptionBoxType, on_delete=models.PROTECT, related_name='user_subscriptions')
    # Статус подписки
    STATUS_CHOICES = [
        ('active', 'Aktywna'),
        ('trialing', 'Okres próbny'), # Можно добавить, если Stripe это поддерживает для твоих планов
        ('paused', 'Wstrzymana'),
        ('canceled', 'Anulowana'),
        ('incomplete', 'Niekompletna'), # Если требует действия от пользователя
        ('incomplete_expired', 'Niekompletna (wygasła)'),
        ('pending_payment', 'Oczekuje na płatność'),
        ('past_due', 'Zaległa płatność'),
    ]
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending_payment')
    start_date = models.DateTimeField(auto_now_add=True, verbose_name="Data utworzenia w systemie")
    current_period_start = models.DateTimeField(verbose_name="Początek bieżącego okresu", blank=True, null=True)
    current_period_end = models.DateTimeField(verbose_name="Koniec bieżącego okresu", blank=True, null=True)
    cancel_at_period_end = models.BooleanField(default=False, verbose_name="Anulować na koniec okresu?")
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True, unique=True, verbose_name="Stripe Subscription ID")
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Stripe Customer ID")
    # Дополнительные поля, если нужны (например, кастомный адрес доставки для этой подписки)
    # ...

    class Meta:
        verbose_name = "Subskrypcja Użytkownika"
        verbose_name_plural = "Subskrypcje Użytkowników"
        ordering = ['-start_date']

    def __str__(self):
        return f"Subskrypcja użytkownika {self.user.username} na {self.box_type.name}"

    def is_active(self):
        return self.status == 'active'