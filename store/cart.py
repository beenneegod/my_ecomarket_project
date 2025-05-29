# store/cart.py

from decimal import Decimal
from django.conf import settings
from .models import Product

class Cart:
    """
    Класс для управления корзиной покупок в сессии.
    """
    def __init__(self, request):
        """
        Инициализация корзины.
        Получает корзину из текущей сессии или создает новую.
        """
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            # Сохраняем пустую корзину в сессии
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    def add(self, product, quantity=1, update_quantity=False):
        """
        Добавить товар в корзину или обновить его количество.
        """
        product_id = str(product.id) # Используем строку для ID товара в качестве ключа JSON

        if product_id not in self.cart:
            self.cart[product_id] = {'quantity': 0, 'price': str(product.price)}

        if update_quantity:
            # Если флаг update_quantity=True, устанавливаем новое количество
            self.cart[product_id]['quantity'] = quantity
        else:
            # Иначе, увеличиваем количество на quantity (обычно на 1)
            self.cart[product_id]['quantity'] += quantity

        # Проверка, чтобы количество не превышало остаток на складе
        if self.cart[product_id]['quantity'] > product.stock:
             self.cart[product_id]['quantity'] = product.stock # Ограничиваем максимальным количеством на складе
             # Можно добавить сообщение для пользователя здесь или в представлении

        # Если количество стало 0 или меньше, удаляем товар
        if self.cart[product_id]['quantity'] <= 0:
             self.remove(product)
        else:
             self.save()

    def remove(self, product):
        """
        Удалить товар из корзины.
        """
        product_id = str(product.id)
        if product_id in self.cart:
            del self.cart[product_id]
            self.save()

    def __iter__(self):
        product_ids = self.cart.keys()
        products = Product.objects.filter(id__in=product_ids)
        cart = self.cart.copy()

        products_in_cart = []
        for product in products:
            item_data = cart[str(product.id)]
            item_data['product_obj'] = product # Используем product_obj в шаблоне
            item_data['total_price'] = Decimal(item_data['price']) * item_data['quantity']
            products_in_cart.append(item_data)

         # Удалить из сессии корзины товары, которых уже нет в БД
        current_product_ids_in_db = [str(p.id) for p in products]
        for product_id_in_session in list(cart.keys()): # list() для безопасного удаления при итерации
            if product_id_in_session not in current_product_ids_in_db:
                del self.cart[product_id_in_session]
        if len(products_in_cart) != len(cart): # Если что-то удалили
            self.save() # Сохранить изменения в сессии

        return iter(products_in_cart)

    def __len__(self):
        """
        Подсчет общего количества товаров в корзине.
        """
        return sum(item['quantity'] for item in self.cart.values())

    def get_total_price(self):
        """
        Подсчет общей стоимости товаров в корзине.
        """
        return sum(Decimal(item['price']) * item['quantity'] for item in self.cart.values())

    def clear(self):
        """
        Удаление корзины из сессии.
        """
        del self.session[settings.CART_SESSION_ID]
        self.save()

    def save(self):
        """
        Помечает сессию как "измененную", чтобы убедиться, что она сохранена.
        """
        self.session.modified = True