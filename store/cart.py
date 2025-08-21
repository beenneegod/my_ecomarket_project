# store/cart.py

from decimal import Decimal
from django.conf import settings
from .models import Product, Coupon # Added Coupon
from django.utils import timezone # Added timezone
import logging

logger = logging.getLogger(__name__)
class Cart:
    def __init__(self, request):
        self.session = request.session
        cart_data = self.session.get(settings.CART_SESSION_ID)
        if not cart_data:
            # Initialize cart and coupon_id if not present
            cart_data = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart_data

        # Sanitize existing cart entries: keep only JSON-serializable fields
        # Allowed keys in each item: 'quantity' (int), 'price' (str)
        changed = False
        for pid, data in list(self.cart.items()):
            if isinstance(data, dict):
                keys_to_remove = [k for k in list(data.keys()) if k not in ('quantity', 'price')]
                for k in keys_to_remove:
                    data.pop(k, None)
                    changed = True
        if changed:
            self.save()

        # Coupon handling
        self.coupon = None
        coupon_id = self.session.get('coupon_id')
        if coupon_id:
            try:
                coupon = Coupon.objects.get(id=coupon_id)
                now = timezone.now()
                if coupon.active and coupon.valid_from <= now and coupon.valid_to >= now:
                    self.coupon = coupon
                else:
                    # Coupon is invalid (e.g., expired, inactive)
                    self.clear_coupon() # This will remove coupon_id from session
            except Coupon.DoesNotExist:
                self.clear_coupon() # Coupon ID in session but no such coupon

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
        if product.stock is not None and self.cart[product_id]['quantity'] > product.stock:
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
            # Если после удаления корзина пуста — полностью очищаем её и купон
            if not self.cart:  # пустой dict
                self.clear()  # также очистит купон и пометит сессию изменённой
            else:
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
            
            raw = cart.get(product_id_str) # Используем .get() для безопасности, хотя ID должен быть
            if raw is None:
                logger.warning(f"CART_DEBUG: Product ID {product_id_str} found in DB but not in cart session copy. Skipping.")
                continue

            # Do NOT mutate session-stored dicts; build a separate item dict for template
            try:
                price_dec = Decimal(raw['price'])
            except Exception:
                # Fallback: coerce to Decimal safely
                price_dec = Decimal(str(raw.get('price', '0')))
            item_for_template = {
                'product_obj': product_instance,
                'quantity': raw.get('quantity', 0),
                'price': price_dec,
                'total_price': price_dec * raw.get('quantity', 0),
            }
            products_in_cart.append(item_for_template)

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
        # Возвращаем Decimal даже если корзина пуста, чтобы избежать ошибок при quantize
        return sum((Decimal(item['price']) * item['quantity'] for item in self.cart.values()), Decimal('0.00'))

    def clear(self):
        """
        Удаление корзины из сессии и сброс купона.
        """
        # del self.session[settings.CART_SESSION_ID] # This would delete the cart items too
        # Instead, clear the cart items and then the coupon
        self.cart = self.session[settings.CART_SESSION_ID] = {}
        self.clear_coupon() # Ensure coupon is cleared when cart is cleared
        self.save()

    def save(self):
        """
        Помечает сессию как "измененную", чтобы убедиться, что она сохранена.
        """
        self.session.modified = True

    def set_coupon(self, coupon):
        """
        Применяет купон к корзине.
        """
        self.session['coupon_id'] = coupon.id
        self.coupon = coupon
        self.save()

    def get_discount(self):
        """
        Возвращает процент скидки из купона, если применён и валиден.
        """
        if self.coupon:
            now = timezone.now()
            if self.coupon.active and self.coupon.valid_from <= now and self.coupon.valid_to >= now:
                return self.coupon.discount # This is an integer percentage
        return 0

    def get_total_price_after_discount(self):
        """
        Возвращает итоговую сумму с учетом скидки по купону.
        """
        total_price = self.get_total_price()
        discount_percentage = self.get_discount()
        if discount_percentage > 0:
            discount_amount = total_price * (Decimal(discount_percentage) / Decimal(100))
            return (total_price - discount_amount).quantize(Decimal('0.01'))
        return total_price.quantize(Decimal('0.01'))
    
    def clear_coupon(self):
        """
        Удаляет купон из сессии (сброс скидки).
        """
        if 'coupon_id' in self.session:
            del self.session['coupon_id']
        # Remove old session keys if they exist, for cleanup
        if 'coupon_code' in self.session:
            del self.session['coupon_code']
        if 'coupon_discount' in self.session:
            del self.session['coupon_discount']
        self.coupon = None
        self.save()

    def get_discount_amount(self):
        """
        Возвращает сумму скидки в валюте (например, PLN).
        """
        total = self.get_total_price()
        total_after = self.get_total_price_after_discount()
        return (total - total_after).quantize(Decimal('0.01'))