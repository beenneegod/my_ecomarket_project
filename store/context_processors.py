# store/context_processors.py

from .cart import Cart
from django.conf import settings

def cart(request):
    """
    Контекстный процессор, который добавляет экземпляр корзины
    в контекст шаблона.
    """
    # Просто возвращаем словарь, где ключ 'cart' - это
    # экземпляр нашего класса Cart, инициализированный текущим запросом.
    # Теперь объект cart будет доступен во всех шаблонах.
    return {'cart': Cart(request)}


def support_email(request):
    """Expose support email addresses to all templates."""
    return {
        'SUPPORT_EMAIL': getattr(settings, 'SUPPORT_EMAIL', None),
        'DEFAULT_FROM_EMAIL': getattr(settings, 'DEFAULT_FROM_EMAIL', None),
    'SUPPORT_PHONE': getattr(settings, 'SUPPORT_PHONE', ''),
    'SUPPORT_ADDRESS': getattr(settings, 'SUPPORT_ADDRESS', ''),
    'RECAPTCHA_SITE_KEY': getattr(settings, 'RECAPTCHA_SITE_KEY', ''),
    }