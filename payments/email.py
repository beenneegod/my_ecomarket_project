# payments/email.py

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from store.models import Order

def send_order_confirmation_email(order: Order):
    """
    Отправляет email с подтверждением заказа клиенту.
    """
    if not order.email:
        print(f"!!! Невозможно отправить email для Заказа #{order.id}: Email клиента не указан.")
        return False # Выходим, если нет email

    subject = f'Подтверждение заказа #{order.id} - EcoMarket'
    recipient_email = order.email
    from_email = settings.DEFAULT_FROM_EMAIL

    # Готовим контекст для шаблонов письма
    context = {
        'order': order,
        'user': order.user, # Передаем пользователя, если он есть
    }

    try:
        # Рендерим текстовую версию письма из шаблона
        plain_message = render_to_string('emails/order_confirmation.txt', context)
        # Опционально: Рендерим HTML версию письма (создадим шаблон позже)
        html_message = render_to_string('emails/order_confirmation.html', context)
        html_message = None # Пока без HTML версии

        send_mail(
            subject,
            plain_message,
            from_email,
            [recipient_email], # Список получателей
            html_message=html_message, # HTML версия (опционально)
            fail_silently=False, # Вызывать исключение, если отправка не удалась
        )
        print(f"Email подтверждения для Заказа #{order.id} успешно отправлен (в консоль).")
        return True
    except Exception as e:
        # Логируем ошибку отправки email
        print(f"!!! Ошибка при отправке email для Заказа #{order.id}: {e}")
        return False