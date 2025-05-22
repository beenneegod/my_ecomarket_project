from django.db.models.signals import post_save
from django.contrib.auth.models import User # Или settings.AUTH_USER_MODEL
from django.dispatch import receiver
from .models import Profile

@receiver(post_save, sender=User) # Используем стандартного User, если settings.AUTH_USER_MODEL это он
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    # Если профиль уже существует и нужно что-то обновить при сохранении User (не для аватара)
    # instance.profile.save() # Это не нужно здесь, т.к. Profile создается пустым