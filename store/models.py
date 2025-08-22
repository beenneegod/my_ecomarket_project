# store/models.py

from django.db import models
from django.conf import settings # Для ссылки на модель пользователя
from django.urls import reverse
from django.utils.text import slugify
import os
def profile_avatar_upload_to(instance, filename: str) -> str:
    """Build a safe per-user S3 key for avatar uploads.
    - avatars/<slug-username>/<slug-name><ext>
    - strips any path components (e.g., C:\\fakepath) and normalizes name
    """
    try:
        base = os.path.basename(filename or '')
    except Exception:
        base = filename or ''
    name, ext = os.path.splitext(base)
    if not ext:
        ext = '.jpg'
    safe_user = slugify(getattr(instance.user, 'username', '') or 'user')
    safe_name = slugify(name or 'avatar')
    return f"avatars/{safe_user}/{safe_name}{ext.lower()}"
from django.utils.module_loading import import_string
from django.core.validators import MinValueValidator, MaxValueValidator

class Category(models.Model):
    """Модель категории товаров"""
    name = models.CharField(max_length=200, db_index=True, verbose_name="Nazwa")
    # Slug - это часть URL, обычно формируется из названия (например, 'kukhonnaya-tekhnika')
    # unique=True гарантирует, что слаги не будут повторяться
    slug = models.SlugField(max_length=200, unique=True, verbose_name="Alias URL")

    class Meta:
        ordering = ('name',)
        verbose_name = 'Kategoria'
        verbose_name_plural = 'Kategorie'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        """Возвращает URL для отображения товаров этой категории."""
        # 'store:product_list_by_category' - это имя URL, которое мы создадим позже
        return reverse('store:product_list_by_category', args=[self.slug])
    
def get_product_image_storage_instance():
    """
    Возвращает экземпляр файлового хранилища в зависимости от settings.DEBUG.
    Вызывается один раз при определении класса Product.
    """
    if not settings.DEBUG:
        storage_path = settings.DEFAULT_FILE_STORAGE # Должен быть 'storages.backends.s3boto3.S3Boto3Storage'
        print(f"[get_product_image_storage_instance] Using S3 Storage: {storage_path}")
    else:
        storage_path = 'django.core.files.storage.FileSystemStorage' # Явно для DEBUG=True
        print(f"[get_product_image_storage_instance] Using FileSystem Storage: {storage_path}")
    
    StorageClass = import_string(storage_path)
    return StorageClass()

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
                            db_index=True,
                            verbose_name="Alias URL")
    description = models.TextField(blank=True, verbose_name="Opis") # Описание может быть необязательным
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cena") # Используем DecimalField для точности
    stock = models.PositiveIntegerField(default=0, verbose_name="Ilość na stanie") # Количество не может быть отрицательным
    image = models.ImageField(
        upload_to='products/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name="Obrazek",
        storage=get_product_image_storage_instance()
    )
    # upload_to создает подпапки по году/месяцу/дню для порядка
    available = models.BooleanField(default=True, verbose_name="Dostępny") # Флаг доступности товара
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data utworzenia") # Дата добавления (автоматически при создании)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Data aktualizacji") # Дата последнего обновления (автоматически при сохранении)
    class Meta:
        verbose_name = "Produkt"
        verbose_name_plural = "Produkty"
        ordering = ['name'] # Сортировка по умолчанию по названию

    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        """Возвращает канонический URL для страницы деталей товара."""
        return reverse('store:product_detail', args=[self.slug])
    
    def save(self, *args, **kwargs):
        if not self.slug or self.slug.strip() == "": # Генерируем, если слаг отсутствует или пустой (пробелы)
            if self.name:
                self.slug = slugify(self.name)
                # Логика проверки уникальности и добавления суффикса
                original_slug = self.slug
                counter = 1
                # Определяем максимальную длину слага с учетом возможного суффикса (например, "-1", "-2")
                # Это базовая реализация, для высокой нагрузки может потребоваться более сложная логика
                base_slug_max_length = self._meta.get_field('slug').max_length - (len(str(Product.objects.count())) + 2) # Примерный расчет

                if len(self.slug) > base_slug_max_length:
                    self.slug = self.slug[:base_slug_max_length]
                    original_slug = self.slug # Обновляем original_slug, если он был урезан

                queryset = Product.objects.filter(slug=self.slug)
                if self.pk: # Если объект уже существует в БД
                    queryset = queryset.exclude(pk=self.pk)

                while queryset.exists():
                    self.slug = f"{original_slug}-{counter}"
                    counter += 1
                    if len(self.slug) > self._meta.get_field('slug').max_length:
                    # Если даже с коротким суффиксом превышаем, это проблема.
                    # Можно либо урезать еще, либо вызвать ошибку, либо использовать UUID в суффиксе.
                    # Для простоты пока оставим как есть, но это место для улучшения.
                        self.slug = self.slug[:self._meta.get_field('slug').max_length] # Обрезаем жестко

                    queryset = Product.objects.filter(slug=self.slug)
                    if self.pk:
                        queryset = queryset.exclude(pk=self.pk)
            else:
            # Если нет имени, слаг не может быть сгенерирован.
            # Если слаг обязателен (null=False), здесь должна быть ошибка или значение по умолчанию.
            # Но так как мы делаем slug не null=False, то до этого доходить не должно, если имя есть.
                pass 
        super().save(*args, **kwargs)

class Coupon(models.Model):
    from django.core.validators import MinValueValidator, MaxValueValidator
    code = models.CharField(max_length=50, unique=True, verbose_name="Kod kuponu")
    valid_from = models.DateTimeField(verbose_name="Początek ważności")
    valid_to = models.DateTimeField(verbose_name="Koniec ważności")
    discount = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Zniżka (%)",
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    active = models.BooleanField(default=True, verbose_name="Aktywny")

    class Meta:
        verbose_name = "Kupon rabatowy"
        verbose_name_plural = "Kupony rabatowe"

    def __str__(self):
        return self.code

class Order(models.Model):
    """Модель заказа"""
    # Связь с пользователем. Используем settings.AUTH_USER_MODEL для гибкости.
    # null=True, blank=True позволят создавать заказы для неавторизованных пользователей (если понадобится)
    # on_delete=models.SET_NULL - если пользователь удален, заказ остается, но без пользователя
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders', verbose_name="Użytkownik")
    # Дополнительные поля для адреса доставки и т.д. можно добавить сюда
    first_name = models.CharField(max_length=100, verbose_name="Imię")
    last_name = models.CharField(max_length=100, verbose_name="Nazwisko")
    email = models.EmailField(verbose_name="Email")
    address_line_1 = models.CharField(max_length=250, verbose_name="Adres (linia 1)")
    address_line_2 = models.CharField(max_length=250, blank=True, verbose_name="Adres (linia 2, opcjonalnie)")
    postal_code = models.CharField(max_length=20, verbose_name="Kod pocztowy")
    city = models.CharField(max_length=100, verbose_name="Miasto")
    # Поле страны пока сделаем простым текстом, можно усложнить позже
    country = models.CharField(max_length=100, default="Polska", verbose_name="Kraj")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data złożenia")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Data aktualizacji")
    paid = models.BooleanField(default=False, verbose_name="Opłacone") # Статус оплаты
    stripe_id = models.CharField(max_length=250, blank=True, verbose_name="ID transakcji Stripe") # Для хранения ID сессии/платежа Stripe
    coupon = models.ForeignKey(Coupon, related_name='orders', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Kupon")
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Zniżka (%)")
    # Флаг, чтобы не отправлять подтверждение повторно при повторах вебхука/таска
    email_sent = models.BooleanField(default=False, verbose_name="Email potwierdzający wysłany")

    class Meta:
        verbose_name = "Zamówienie"
        verbose_name_plural = "Zamówienia"
        ordering = ['-created_at'] # Сортировка по умолчанию - сначала новые

    def __str__(self):
        return f"Zamówienie №{self.id}"

    def get_total_cost(self):
        total = sum(item.get_cost() for item in self.items.all())
        if self.discount:
            return total - (total * (self.discount / 100))
        return total

class OrderItem(models.Model):
    """Модель элемента заказа (конкретный товар в заказе)"""
    # Связь с заказом. related_name='items' позволяет обращаться к элементам заказа через order.items.all()
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE, verbose_name="Zamówienie")
    # Связь с товаром. related_name='order_items' - для обратного доступа (product.order_items.all())
    product = models.ForeignKey(Product, related_name='order_items', on_delete=models.PROTECT, verbose_name="Produkt") # PROTECT - не даст удалить товар, если он есть в заказах
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cena") # Цена товара НА МОМЕНТ покупки
    quantity = models.PositiveIntegerField(default=1, verbose_name="Ilość")

    class Meta:
        verbose_name = "Pozycja zamówienia"
        verbose_name_plural = "Pozycje zamówienia"
        # Уникальность пары заказ-товар, чтобы один товар не добавлялся дважды в один заказ как отдельный OrderItem
        unique_together = ('order', 'product')

    def __str__(self):
        return f"{self.quantity} x {self.product.name} w zamówieniu №{self.order.id}"

    def get_cost(self):
        """Возвращает стоимость данного элемента заказа (цена * количество)"""
        return self.price * self.quantity
    

class UserCoupon(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coupons', verbose_name="Użytkownik")
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='user_coupons', verbose_name="Kupon")
    awarded_at = models.DateTimeField(auto_now_add=True, verbose_name="Data przyznania")
    is_used = models.BooleanField(default=False, verbose_name="Czy wykorzystany")
    # Дата использования купона (если применён к заказу)
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="Data wykorzystania")
    # Ссылка на заказ, в котором купон был использован (если применимо)
    order = models.ForeignKey(
        'store.Order',  # строковая ссылка, чтобы избежать проблем порядка импорта
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_user_coupons',
        verbose_name="Zamówienie (wykorzystanie kuponu)"
    )
    challenge_source = models.ForeignKey(
        'challenges.Challenge',  # Используем строковую ссылку для избежания циклического импорта
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='awarded_user_coupons',
        verbose_name="Wyzwanie (źródło kuponu)"
    )

    class Meta:
        verbose_name = "Kupon użytkownika"
        verbose_name_plural = "Kupony użytkowników"
        unique_together = ('user', 'coupon') # Пользователь может получить конкретный купон только один раз
        ordering = ['-awarded_at']

    def __str__(self):
        return f"Kupon {self.coupon.code} dla {self.user.username} (Przyznany: {self.awarded_at.strftime('%Y-%m-%d %H:%M')})"


class Profile(models.Model): # Без отступа в начале строки
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(
    upload_to=profile_avatar_upload_to,
        null=True,
        blank=True,
        storage=get_product_image_storage_instance()
    )
    bio = models.TextField(blank=True, null=True, verbose_name="O sobie")
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Stripe Customer ID")
    eco_points = models.PositiveIntegerField(default=0, verbose_name="Эко-очки")
    last_points_update = models.DateTimeField(null=True, blank=True, verbose_name="Последнее обновление очков")
    
    class Meta:
        verbose_name = "Profil użytkownika"
        verbose_name_plural = "Profile użytkowników"

    def __str__(self):
        return f"Profil użytknika {self.user.username}"

    @property
    def avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        else:
            from django.templatetags.static import static
            return static('img/default_avatar.svg')
        


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


class ProductRating(models.Model):
    """Star rating for products, 1-5, one per user per product."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ratings', verbose_name="Produkt")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='product_ratings', verbose_name="Użytkownik")
    value = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="Ocena (1-5)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Utworzono")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Zaktualizowano")

    class Meta:
        verbose_name = "Ocena produktu"
        verbose_name_plural = "Oceny produktów"
        unique_together = ("product", "user")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} - {self.user} ({self.value})"