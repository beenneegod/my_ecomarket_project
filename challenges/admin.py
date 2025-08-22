# challenges/admin.py
from django.contrib import admin, messages
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from .models import Challenge, UserChallengeParticipation, Badge, UserBadge, EcoPointEvent
from store.models import Profile

@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'start_date', 'end_date', 'points_for_completion', 'is_active_now', 'is_template', 'is_active')
    list_filter = ('status', 'is_template', 'is_active', 'start_date', 'end_date')
    search_fields = ('title', 'description')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('status', 'points_for_completion')
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'short_description', 'description', 'image'),
            'description': 'Podstawowe informacje o wyzwaniu.'
        }),
        ('Terminy i status', {
            'fields': ('start_date', 'end_date', 'status', 'is_template', 'recurrence_type', 'max_future_instances', 'is_active'),
            'description': 'Ustaw daty, status, czy to szablon powtarzalny oraz widoczność.'
        }),
        ('Nagrody', {
            'fields': ('points_for_completion', 'badge_name_reward', 'badge_icon_class_reward'),
            'description': 'Punkty i odznaka za ukończenie wyzwania.'
        }),
    )

    @admin.display(boolean=True, description="Aktywne teraz?")
    def is_active_now(self, obj):
        return obj.is_active_now()

@admin.register(UserChallengeParticipation)
class UserChallengeParticipationAdmin(admin.ModelAdmin):
    list_display = ('user', 'challenge', 'status', 'joined_at', 'completed_at')
    list_filter = ('status', 'challenge', 'joined_at')
    search_fields = ('user__username', 'challenge__title', 'user_notes')
    list_editable = ('status',)
    readonly_fields = ('user', 'challenge', 'joined_at')
    actions = ['approve_completion', 'reject_completion']

    @admin.action(description="Zatwierdź ukończenie i przyznaj punkty")
    def approve_completion(self, request, queryset):
        updated = 0
        awarded = 0
        with transaction.atomic():
            for part in queryset.select_related('challenge', 'user'):
                if part.status == 'completed_approved':
                    continue
                ch = part.challenge
                part.status = 'completed_approved'
                part.completed_at = part.completed_at or timezone.now()
                part.save(update_fields=['status', 'completed_at'])
                updated += 1

                # Idempotent award: skip if event for this user+challenge already exists
                if not EcoPointEvent.objects.filter(user=part.user, challenge=ch, source='challenge').exists():
                    profile, _ = Profile.objects.get_or_create(user=part.user)
                    Profile.objects.filter(pk=profile.pk).update(
                        eco_points=F('eco_points') + (ch.points_for_completion or 0),
                        last_points_update=timezone.now(),
                    )
                    EcoPointEvent.objects.create(
                        user=part.user,
                        amount=ch.points_for_completion or 0,
                        source='challenge',
                        challenge=ch,
                    )
                    awarded += 1
        messages.success(request, f"Zatwierdzono: {updated}, punkty przyznane: {awarded}")

    @admin.action(description="Odrzuć ukończenie (bez punktów)")
    def reject_completion(self, request, queryset):
        count = 0
        with transaction.atomic():
            for part in queryset:
                if part.status in ('completed_approved', 'completed_pending_review'):
                    part.status = 'in_progress'
                    part.save(update_fields=['status'])
                    count += 1
        messages.info(request, f"Przywrócono status 'w trakcie' dla: {count}")

@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon_class_preview', 'description_short')
    search_fields = ('name', 'description')

    @admin.display(description="Ikona")
    def icon_class_preview(self, obj):
        if obj.icon_class:
            from django.utils.html import format_html
            return format_html('<i class="{} fs-4"></i>', obj.icon_class)
        return "-"
    
    @admin.display(description="Krótki opis")
    def description_short(self, obj):
        if obj.description and len(obj.description) > 75:
            return obj.description[:75] + '...'
        return obj.description or "-"


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ('user', 'badge', 'awarded_at')
    list_filter = ('badge', 'awarded_at')
    search_fields = ('user__username', 'badge__name')
    readonly_fields = ('user', 'badge', 'awarded_at')

    def has_add_permission(self, request): # Значки обычно выдаются автоматически или через действия
        return False


@admin.register(EcoPointEvent)
class EcoPointEventAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "source", "challenge", "created_at")
    list_filter = ("source", "created_at")
    search_fields = ("user__username", "challenge__title")