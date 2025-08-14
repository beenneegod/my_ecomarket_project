# challenges/management/commands/create_recurring_challenges.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from challenges.models import Challenge

class Command(BaseCommand):
    help = 'Creates new instances of recurring challenges for the upcoming week and archives old ones.'

    def handle(self, *args, **options):
        now = timezone.now()
        local_now = timezone.localtime(now)
        self.stdout.write(f"System time: {local_now.strftime('%Y-%m-%d %H:%M:%S')} (local)")
        
        # Расчет начала следующей недели (следующий понедельник)
        days_until_monday = (0 - now.weekday() + 7) % 7
        if days_until_monday == 0: # если сегодня понедельник, берем следующий
            days_until_monday = 7
        
        upcoming_monday = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        upcoming_sunday = (upcoming_monday + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)

        self.stdout.write(f"System time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Calculated upcoming week: Monday {upcoming_monday.strftime('%Y-%m-%d')} to Sunday {upcoming_sunday.strftime('%Y-%m-%d')}")

        # Найти все шаблоны челленджей
        challenge_templates = Challenge.objects.filter(is_template=True, is_active=True)

        if not challenge_templates.exists():
            self.stdout.write(self.style.WARNING('No active challenge templates found.'))
        
        for template in challenge_templates:
            self.stdout.write(f"Processing template: '{template.title}'")

            # Проверяем, не создан ли уже челлендж на основе этого шаблона на предстоящую неделю
            if Challenge.objects.filter(template_challenge=template, start_date=upcoming_monday).exists():
                self.stdout.write(self.style.NOTICE(f"  -> Challenge for this week already exists. Skipping."))
                continue

            # Формируем новое имя для экземпляра челленджа
            instance_name = f"{template.title} ({upcoming_monday.strftime('%d.%m')}-{upcoming_sunday.strftime('%d.%m.%Y')})"
            
            # Создаем новый экземпляр
            new_challenge = Challenge.objects.create(
                title=instance_name,
                short_description=template.short_description,
                description=template.description,
                points_for_completion=template.points_for_completion,
                start_date=upcoming_monday,
                end_date=upcoming_sunday,
                image=template.image,
                badge_name_reward=template.badge_name_reward,
                badge_icon_class_reward=template.badge_icon_class_reward,
                status='upcoming', # Новый челлендж будет "предстоящим"
                is_template=False,
                is_active=True,
                template_challenge=template
            )

            self.stdout.write(self.style.SUCCESS(f"  -> Successfully created instance: '{new_challenge.title}'"))

        # --- Логика архивации старых челленджей ---
        one_week_ago = now - timedelta(days=7)
        old_challenges_to_archive = Challenge.objects.filter(
            is_template=False, 
            end_date__lt=one_week_ago,
            status__in=['active', 'upcoming'] # Архивируем только те, что "зависли" в статусе active или upcoming
        )

        if old_challenges_to_archive.exists():
            updated_count = old_challenges_to_archive.update(status='completed_period')
            self.stdout.write(self.style.SUCCESS(f"\nArchived {updated_count} old challenge instances."))
        else:
            self.stdout.write(self.style.NOTICE("No old challenge instances to archive."))