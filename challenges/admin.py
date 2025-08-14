# challenges/admin.py
from django.contrib import admin
from .models import Challenge, UserChallengeParticipation, Badge, UserBadge

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
            'fields': ('start_date', 'end_date', 'status', 'is_template', 'is_active'),
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
    # Поля для ручного подтверждения, если нужно
    # actions = ['approve_completion', 'reject_completion'] 
    # def approve_completion(self, request, queryset):
    #     # Логика подтверждения и начисления очков/значков
    #     pass
    # def reject_completion(self, request, queryset):
    #     pass

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