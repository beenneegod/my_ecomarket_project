from background_task import background
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model

def send_winner_notification_email_task(user_id, place, coupon_code, discount_value):
    """
    Фоновая задача для отправки email победителю челленджа.
    """
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        if not user.email:
            print(f"!!! TASK: Nie można wysłać email do użytkownika #{user.id}: Brak adresu email.")
            return False

        subject = f'Gratulacje! Jesteś zwycięzcą w EcoMarket!'
        recipient_email = user.email
        from_email = settings.DEFAULT_FROM_EMAIL

        context = {
            'user': user,
            'place': place,
            'coupon_code': coupon_code,
            'discount_value': discount_value,
        }

        plain_message = render_to_string('challenges/emails/winner_notification.txt', context)
        html_message = render_to_string('challenges/emails/winner_notification.html', context)

        send_mail(
            subject,
            plain_message,
            from_email,
            [recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        print(f"TASK: Email zwycięzcy dla użytkownika #{user.id} wysłany.")
        return True
    except User.DoesNotExist:
        print(f"!!! TASK ERROR: Użytkownik z ID {user_id} nie istnieje. Email nie wysłany.")
        return False
    except Exception as e:
        print(f"!!! TASK ERROR: Błąd przy wysyłaniu emaila zwycięzcy dla użytkownika #{user_id}: {e}")
        return False

send_winner_notification_email_task = background(schedule=5)(send_winner_notification_email_task)
