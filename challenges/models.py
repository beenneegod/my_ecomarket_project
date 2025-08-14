# challenges/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
import re
import uuid
from store.models import Coupon

class Challenge(models.Model):
    STATUS_CHOICES = [
        ('upcoming', 'Nadchodzące'),
        ('active', 'Aktywne'),
        ('completed', 'Ukończone (przez użytkownika)'),
        ('failed', 'Nieukończone (przez użytkownika)'),
        ('completed_period', 'Zakończone (okres minął)'),
        ('archived', 'Zarchiwizowane'),
    ]

    title = models.CharField(max_length=200, verbose_name="Nazwa wyzwania")
    short_description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Krótki opis")
    description = models.TextField(verbose_name="Pełny opis")
    points_for_completion = models.IntegerField(default=10, verbose_name="Punkty za ukończenie")
    start_date = models.DateTimeField(verbose_name="Data rozpoczęcia")
    end_date = models.DateTimeField(verbose_name="Data zakończenia")
    
    image = models.ImageField(upload_to='challenges_images/', null=True, blank=True, verbose_name="Образек wyzwania")
    
    badge_name_reward = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nazwa odznaki za wyzwanie")
    badge_icon_class_reward = models.CharField(max_length=50, blank=True, null=True, verbose_name="CSS klasa ikony odznaki")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming', verbose_name="Status")
    
    # --- НОВЫЕ ПОЛЯ ---
    is_template = models.BooleanField(default=False, verbose_name="Szablon powtarzalny")
    is_active = models.BooleanField(default=True, verbose_name="Aktywne (widoczne)")
    template_challenge = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instances',
        verbose_name="Szablon tego wyzwania"
    )

    slug = models.SlugField(max_length=220, unique=True, blank=True, verbose_name="Slug (do URL)")
    reward_coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reward_challenges',
        verbose_name="Kupón za ukończenie wyzwania"
    )

    class Meta:
        verbose_name = "Wyzwanie"
        verbose_name_plural = "Wyzwania"
        ordering = ['start_date']

    def __str__(self):
        base_name = self.title
        # Проверяем, содержит ли уже заголовок дату в формате (ДД.ММ-ДД.ММ.ГГГГ)
        if re.search(r'\(\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{4}\)$', self.title):
            pass # Если да, оставляем как есть
        elif self.start_date and self.end_date and not self.is_template:
            base_name = f"{self.title} ({self.start_date.strftime('%d.%m.%Y')} - {self.end_date.strftime('%d.%m.%Y')})"

        if self.is_template:
            base_name += " (Шаблон)"
        return base_name

    def get_absolute_url(self):
        return reverse('challenges:challenge_detail', kwargs={'slug': self.slug})

    def is_active_now(self):
        now = timezone.now()
        return self.start_date <= now <= self.end_date and self.status == 'active'
    
    def can_join(self):
        # Можно добавить условия, например, если челлендж не требует регистрации заранее
        return self.is_active_now()


class UserChallengeParticipation(models.Model):
    PARTICIPATION_STATUS_CHOICES = [
        ('joined', 'Dołączył'),
        ('in_progress', 'W trakcie'),
        ('completed_pending_review', 'Ukończone (oczekuje na weryfikację)'),
        ('completed_approved', 'Ukończone (zatwierdzone)'),
        ('failed', 'Nieukończone'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='challenge_participations')
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='participants')
    
    status = models.CharField(max_length=30, choices=PARTICIPATION_STATUS_CHOICES, default='joined')
    joined_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Data faktycznego ukończenia")
    
    # Поле для заметок пользователя или загрузки доказательств (если требуется)
    user_notes = models.TextField(blank=True, null=True, verbose_name="Notatki użytkownika/Raport")
    # proof_image = models.ImageField(upload_to='challenge_proofs/', blank=True, null=True, verbose_name="Доказательство (изображение)")

    class Meta:
        verbose_name = "Udział w wyzwaniu"
        verbose_name_plural = "Udziały w wyzwaniach"
        unique_together = ('user', 'challenge') # Пользователь может участвовать в челлендже только один раз
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.user.username} - {self.challenge.title} ({self.get_status_display()})"

class Badge(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nazwa odznaki")
    description = models.TextField(blank=True, null=True, verbose_name="Opis")
    icon_class = models.CharField(max_length=50, blank=True, null=True, verbose_name="CSS klasa ikony") # e.g., 'bi bi-star-fill text-warning'
    # image = models.ImageField(upload_to='badges/', blank=True, null=True, verbose_name="Изображение значка")
    # criteria_description = models.TextField(blank=True, null=True, verbose_name="За что выдается") # Можно связать с Challenge

    class Meta:
        verbose_name = "Odznaka"
        verbose_name_plural = "Odznaki"

    def __str__(self):
        return self.name

class UserBadge(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='badges_earned')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='awarded_to_users')
    awarded_at = models.DateTimeField(auto_now_add=True)
    # challenge_completed = models.ForeignKey(Challenge, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Челлендж (если значок за него)")

    class Meta:
        verbose_name = "Odznaka użytkownika"
        verbose_name_plural = "Odznaki użytkowników"
        unique_together = ('user', 'badge') # Пользователь получает каждый значок только один раз
        ordering = ['-awarded_at']

    def __str__(self):
        return f"Odznaka '{self.badge.name}' dla {self.user.username}"