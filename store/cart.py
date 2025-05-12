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
        """
        Перебор элементов в корзине и получение товаров из базы данных.
        """
        product_ids = self.cart.keys()
        # Получаем объекты товаров и добавляем их в корзину
        products = Product.objects.filter(id__in=product_ids)

        cart = self.cart.copy() # Создаем копию словаря корзины
        for product in products:
            cart[str(product.id)]['product'] = product # Добавляем объект Product

        # Перебираем копию корзины, чтобы выдать элементы
        for item in cart.values():
            item['price'] = Decimal(item['price']) # Конвертируем цену обратно в Decimal
            item['total_price'] = item['price'] * item['quantity'] # Считаем общую стоимость для элемента
            yield item # Возвращаем элемент (как генератор)

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