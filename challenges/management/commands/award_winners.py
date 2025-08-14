# challenges/management/commands/award_winners.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction

from challenges.models import Coupon
from store.models import Profile # У вас Profile в приложении store

User = get_user_model()

class Command(BaseCommand):
    help = 'Awards top users from the leaderboard with discount coupons at the beginning of the month.'

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        self.stdout.write(f"--- Running monthly awards on {now.strftime('%Y-%m-%d %H:%M:%S')} ---")

        # --- 1. Определение победителей ---
        # Находим Топ-3 пользователей по eco_points
        # select_related('user') оптимизирует запрос, чтобы сразу получить данные пользователя
        top_profiles = Profile.objects.select_related('user').filter(eco_points__gt=0).order_by('-eco_points')[:3]

        if not top_profiles:
            self.stdout.write(self.style.WARNING("No users with eco_points > 0 found. No winners to award."))
            return

        # --- 2. Определение наград ---
        # Структура: (место, процент скидки)
        awards = {
            0: 20, # 1-е место (индекс 0)
            1: 15, # 2-е место (индекс 1)
            2: 10, # 3-е место (индекс 2)
        }

        # --- 3. Создание купонов ---
        valid_from_date = now
        valid_to_date = now + timedelta(days=30) # Купон действует 30 дней

        for i, profile in enumerate(top_profiles):
            winner = profile.user
            discount_value = awards.get(i)

            if not discount_value:
                continue # На случай, если победителей меньше 3

            # Создаем уникальный код купона
            month_year_str = now.strftime("%b%Y").upper() # напр. JUN2024
            coupon_code = f"TOP{i+1}-{month_year_str}-{winner.username.upper()}"

            # Проверяем, не был ли уже выдан купон этому пользователю за этот месяц
            if Coupon.objects.filter(user=winner, code__startswith=f"TOP{i+1}-{month_year_str}").exists():
                self.stdout.write(self.style.NOTICE(f"User '{winner.username}' has already received a TOP-{i+1} award for {month_year_str}. Skipping."))
                continue

            Coupon.objects.create(
                user=winner,
                code=coupon_code,
                discount_type='percent',
                value=discount_value,
                valid_from=valid_from_date,
                valid_to=valid_to_date,
                is_active=True,
                max_usage=1, # Персональный купон на одно использование
                min_purchase_amount=50.00 # Например, минимальная сумма покупки 50 PLN
            )

            self.stdout.write(self.style.SUCCESS(
                f"Created a {discount_value}% discount coupon '{coupon_code}' for winner #{i+1}: '{winner.username}'"
            ))

            # TODO: Отправить email-уведомление победителю
            # Здесь можно будет добавить вызов фоновой задачи для отправки email
            # send_winner_notification_email.delay(winner.id, coupon_code)

        self.stdout.write("--- Monthly awards process finished. ---")