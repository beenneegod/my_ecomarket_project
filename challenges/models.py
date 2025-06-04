# challenges/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse

class Challenge(models.Model):
    STATUS_CHOICES = [
        ('upcoming', 'Nadchodzące'),
        ('active', 'Aktywne'),
        ('completed', 'Zakończone (okres minął)'),
        ('archived', 'Zarchiwizowane'),
    ]
    title = models.CharField(max_length=200, verbose_name="Nazwa wyzwania")
    slug = models.SlugField(max_length=220, unique=True, blank=True, verbose_name="Slug (do URL)")
    description = models.TextField(verbose_name="Pełny opis i zasady")
    short_description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Krótki opis (do listy)")
    image = models.ImageField(upload_to='challenges_images/', blank=True, null=True, verbose_name="Obrazek wyzwania")
    start_date = models.DateTimeField(verbose_name="Data rozpoczęcia")
    end_date = models.DateTimeField(verbose_name="Data zakończenia")
    points_for_completion = models.PositiveIntegerField(default=0, verbose_name="Punkty za ukończenie")
    badge_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nazwa odznaki (jeśli jest)")
    badge_icon_class = models.CharField(max_length=50, blank=True, null=True, verbose_name="CSS klasa ikony odznaki") # e.g., 'bi bi-award-fill'
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='upcoming', verbose_name="Status wyzwania")
    is_recurring = models.BooleanField(default=False, verbose_name="Czy wyzwanie cykliczne?")
    # recur_frequency = models.CharField(...) # Если да, то как часто (еженедельно, ежемесячно) - это усложнит логику

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Eko-Wyzwanie"
        verbose_name_plural = "Eko-Wyzwania"
        ordering = ['-start_date', 'title']

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify # Импорт здесь, чтобы избежать циклического импорта на уровне модуля
            self.slug = slugify(self.title)
            # Добавить логику уникальности слага, если нужно
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

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

# Модель для очков пользователя можно добавить в store.Profile
# или создать отдельно, если нужна более сложная история начисления очков.
# Давайте пока предположим, что очки будут в store.Profile.
# В store/models.py, в класс Profile, можно добавить:
# eco_points = models.PositiveIntegerField(default=0, verbose_name="Эко-очки")
# last_points_updated_at = models.DateTimeField(null=True, blank=True)

class Badge(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nazwa odznaki")
    description = models.TextField(blank=True, null=True, verbose_name="Opis")
    icon_class = models.CharField(max_length=50, blank=True, null=True, verbose_name="CSS klasa ikony") # e.g., 'bi bi-star-fill text-warning'
    # image = models.ImageField(upload_to='badges/', blank=True, null=True, verbose_name="Изображение значка")
    # criteria_description = models.TextField(blank=True, null=True, verbose_name="За что выдается") # Можно связать с Challenge

    class Meta:
        verbose_name = "Odznaka (Badge)"
        verbose_name_plural = "Odznaki (Badge)"

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
        return f"Значок '{self.badge.name}' для {self.user.username}"