# store/models.py

from django.db import models
from django.conf import settings # Для ссылки на модель пользователя
from django.urls import reverse

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
                                 verbose_name="Категория")
    name = models.CharField(max_length=255, verbose_name="Название")
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
    # --- Начало блока с отступом (4 пробела) ---
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    # Если default_avatar.png в static/img/, то default в ImageField лучше убрать или указать путь относительно MEDIA_ROOT
    # Логика для дефолтного аватара теперь полностью в avatar_url
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(blank=True, null=True, verbose_name="O sobie")

    class Meta:
        # --- Начало блока с еще одним уровнем отступа (еще 4 пробела, итого 8) ---
        verbose_name = "Profil użytkownika"
        verbose_name_plural = "Profile użytkowników"
        # --- Конец блока Meta ---

    def __str__(self):
        # --- Начало блока с отступом для метода (еще 4 пробела, итого 8) ---
        return f"Profil użytkownika {self.user.username}"
        # --- Конец блока __str__ ---

    @property
    def avatar_url(self):
        # --- Начало блока с отступом для метода (еще 4 пробела, итого 8) ---
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        else:
            # Этот импорт здесь, чтобы избежать циклических зависимостей на уровне модуля
            from django.templatetags.static import static
            return static('img/default_avatar.png')