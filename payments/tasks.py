# payments/tasks.py
from background_task import background
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from store.models import Order, UserSubscription  # Импортируем модель Order

@background(schedule=5) # Задача будет запущена через 5 секунд после вызова
def send_order_confirmation_email_task(order_id):
    """
    Фоновая задача для отправки email с подтверждением заказа.
    """
    try:
        order = Order.objects.get(id=order_id)
        if not order.email:
            print(f"!!! TASK: Невозможно отправить email для Заказа #{order.id}: Email клиента не указан.")
            return False

        subject = f'Подтверждение заказа #{order.id} - EcoMarket' # Используйте f-string для удобства
        recipient_email = order.email
        from_email = settings.DEFAULT_FROM_EMAIL

        context = {
            'order': order,
            'user': order.user,
        }

        plain_message = render_to_string('emails/order_confirmation.txt', context)
        html_message = render_to_string('emails/order_confirmation.html', context) # HTML версия

        send_mail(
            subject,
            plain_message,
            from_email,
            [recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        print(f"TASK: Email подтверждения для Заказа #{order.id} успешно отправлен.")
        return True
    except Order.DoesNotExist:
        print(f"!!! TASK ERROR: Заказ с ID {order_id} не найден. Email не отправлен.")
        return False
    except Exception as e:
        print(f"!!! TASK ERROR: Ошибка при отправке email для Заказа #{order_id}: {e}")
        # Здесь можно добавить более продвинутое логирование или повторные попытки,
        # но для начала достаточно этого.
        return False
    

@background(schedule=10) # Запускаем с небольшой задержкой
def send_subscription_confirmation_email_task(user_subscription_id):
    """
    Фоновая задача для отправки email с подтверждением подписки.
    """
    try:
        user_sub = UserSubscription.objects.select_related('user', 'box_type').get(id=user_subscription_id) # select_related для оптимизации

        if not user_sub.user or not user_sub.user.email:
            # Если пользователя нет или у него нет email (например, анонимная подписка, если бы она была возможна)
            # или если пользователь есть, но email не указан.
            print(f"!!! TASK: Невозможно отправить email для UserSubscription #{user_sub.id}: Email клиента не указан или пользователь отсутствует.")
            return False

        subject = f'Potwierdzenie subskrypcji: {user_sub.box_type.name} - EcoMarket'
        recipient_email = user_sub.user.email
        from_email = settings.DEFAULT_FROM_EMAIL

        context = {
            'user_subscription': user_sub,
            # 'user': user_sub.user # Уже доступно через user_subscription.user в шаблоне
        }

        plain_message = render_to_string('emails/subscription_confirmation.txt', context)
        html_message = render_to_string('emails/subscription_confirmation.html', context)

        send_mail(
            subject,
            plain_message,
            from_email,
            [recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        print(f"TASK: Email подтверждения подписки #{user_sub.id} ({user_sub.box_type.name}) успешно отправлен для {user_sub.user.email}.")
        return True
    except UserSubscription.DoesNotExist:
        print(f"!!! TASK ERROR: UserSubscription с ID {user_subscription_id} не найдена. Email не отправлен.")
        return False
    except Exception as e:
        print(f"!!! TASK ERROR: Ошибка при отправке email для UserSubscription #{user_subscription_id}: {e}")
        return False
    

@background(schedule=10)
def send_subscription_canceled_email_task(user_subscription_id):
    """
    Фоновая задача для отправки email об отмене подписки.
    """
    try:
        user_sub = UserSubscription.objects.select_related('user', 'box_type').get(id=user_subscription_id)

        if not user_sub.user or not user_sub.user.email:
            print(f"!!! TASK: Невозможно отправить email (cancel notice) для UserSubscription #{user_sub.id}: Email клиента не указан или пользователь отсутствует.")
            return False

        subject = f'Twoja subskrypcja "{user_sub.box_type.name}" została anulowana - EcoMarket'
        recipient_email = user_sub.user.email
        from_email = settings.DEFAULT_FROM_EMAIL

        context = {'user_subscription': user_sub}
        plain_message = render_to_string('emails/subscription_canceled_notice.txt', context)
        html_message = render_to_string('emails/subscription_canceled_notice.html', context)

        send_mail(
            subject, plain_message, from_email, [recipient_email],
            html_message=html_message, fail_silently=False,
        )
        print(f"TASK: Email (cancel notice) для UserSubscription #{user_sub.id} ({user_sub.box_type.name}) успешно отправлен для {user_sub.user.email}.")
        return True
    except UserSubscription.DoesNotExist:
        print(f"!!! TASK ERROR: UserSubscription (cancel notice) с ID {user_subscription_id} не найдена. Email не отправлен.")
        return False
    except Exception as e:
        print(f"!!! TASK ERROR: Ошибка при отправке email (cancel notice) для UserSubscription #{user_subscription_id}: {e}")
        return False
    


@background(schedule=10)
def send_payment_failed_email_task(user_subscription_id):
    """
    Фоновая задача для отправки email о проблеме с оплатой подписки.
    """
    try:
        user_sub = UserSubscription.objects.select_related('user', 'box_type').get(id=user_subscription_id)
        if not user_sub.user or not user_sub.user.email:
            print(f"!!! TASK: Невозможно отправить email (payment failed) для UserSubscription #{user_sub.id}: Email клиента не указан или пользователь отсутствует.")
            return False

        subject = f'Problem z płatnością za subskrypcję "{user_sub.box_type.name}" - EcoMarket'
        from_email = settings.DEFAULT_FROM_EMAIL
        context = {'user_subscription': user_sub}
        plain_message = render_to_string('emails/subscription_payment_failed.txt', context)
        html_message = render_to_string('emails/subscription_payment_failed.html', context)

        send_mail(
            subject, plain_message, from_email, [user_sub.user.email], # Убедитесь, что from_email определен
            html_message=html_message, fail_silently=False,
        )
        print(f"TASK: Email (payment failed) для UserSubscription #{user_sub.id} ({user_sub.box_type.name}) успешно отправлен для {user_sub.user.email}.")
        return True
    except UserSubscription.DoesNotExist: # и другие except блоки
        print(f"!!! TASK ERROR: UserSubscription (payment failed) с ID {user_subscription_id} не найдена. Email не отправлен.")
        return False
    except Exception as e:
        print(f"!!! TASK ERROR: Ошибка при отправке email (payment failed) для UserSubscription #{user_subscription_id}: {e}")
        return False