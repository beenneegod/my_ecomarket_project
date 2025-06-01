# store/cart.py

from decimal import Decimal
from django.conf import settings
from .models import Product
import logging

logger = logging.getLogger(__name__)
class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    # First definition of add method removed (lines 17-35) due to F811 redefinition.

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
        # Используем logger.debug() или logger.info() вместо print()
        logger.info(f"CART_DEBUG: Product IDs in session cart: {list(product_ids)}")

        products = Product.objects.filter(id__in=product_ids)
        logger.info(f"CART_DEBUG: Products fetched from DB: {[(p.id, p.name, p.slug) for p in products]}")

        cart = self.cart.copy()

        products_in_cart = []
        for product_instance in products: # Переименовал для ясности
            product_id_str = str(product_instance.id)
            if not product_instance.slug: # ПРОВЕРКА ПРЯМО ЗДЕСЬ
                logger.error(f"CART_CRITICAL_DEBUG: Product ID {product_instance.id} ('{product_instance.name}') has an empty or NULL slug ('{product_instance.slug}') right after fetching from DB!")
            
            item_data = cart.get(product_id_str) # Используем .get() для безопасности, хотя ID должен быть
            if item_data is None:
                logger.warning(f"CART_DEBUG: Product ID {product_id_str} found in DB but not in cart session copy. Skipping.")
                continue

            item_data['product_obj'] = product_instance 
            item_data['total_price'] = Decimal(item_data['price']) * item_data['quantity']
            products_in_cart.append(item_data)

        current_product_ids_in_db = [str(p.id) for p in products]
        ids_removed_from_session = []
        for product_id_in_session in list(cart.keys()): 
            if product_id_in_session not in current_product_ids_in_db:
                ids_removed_from_session.append(product_id_in_session)
                del self.cart[product_id_in_session]
        
        if ids_removed_from_session:
            logger.info(f"CART_DEBUG: Product IDs removed from session because not in DB: {ids_removed_from_session}")
            self.save() 

        logger.info(f"CART_DEBUG: Final products_in_cart to be iterated by template: {[{'id': item['product_obj'].id, 'name': item['product_obj'].name, 'slug': item['product_obj'].slug, 'qty': item['quantity']} for item in products_in_cart]}")
        
        # Дополнительная проверка непосредственно перед возвратом
        for item_for_template in products_in_cart:
            if not item_for_template['product_obj'].slug:
                logger.error(f"CART_CRITICAL_DEBUG_FINAL_CHECK: Product ID {item_for_template['product_obj'].id} ('{item_for_template['product_obj'].name}') has slug ('{item_for_template['product_obj'].slug}') before returning to template!")

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