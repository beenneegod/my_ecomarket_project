from django.contrib import admin
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from .models import Post, Comment, BlogBan

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'author', 'status', 'published_at', 'created_at')
    list_filter = ('status', 'created_at', 'published_at', 'author')
    search_fields = ('title', 'body')
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('author',)
    date_hierarchy = 'published_at'
    ordering = ('status', '-published_at')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        'author', 'post', 'created_at', 'active', 'removed_at', 'removed_by', 'ip_address'
    )
    list_filter = ('active', 'created_at', 'updated_at', 'author', 'removed_at', 'removed_by')
    search_fields = ('author__username', 'post__title', 'body', 'ip_address')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    actions = [
        'approve_comments', 'disapprove_comments',
        'soft_remove_comments', 'restore_comments',
        'ban_authors_24h', 'ban_ips_24h'
    ]

    def approve_comments(self, request, queryset):
        queryset.update(active=True)
    approve_comments.short_description = "Zatwierdź wybrane komentarze"

    def disapprove_comments(self, request, queryset):
        queryset.update(active=False)
    disapprove_comments.short_description = "Odrzuć wybrane komentarze"

    def soft_remove_comments(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(active=False, removed_at=now, removed_by=request.user)
        self.message_user(request, f"Oznaczono jako usunięte: {updated}")
    soft_remove_comments.short_description = "Miękkie usunięcie (active=False, removed_*)"

    def restore_comments(self, request, queryset):
        updated = queryset.update(active=True, removed_at=None, removed_by=None, remove_reason='')
        self.message_user(request, f"Przywrócono: {updated}")
    restore_comments.short_description = "Przywróć komentarze"

    def ban_authors_24h(self, request, queryset):
        until = timezone.now() + timedelta(hours=24)
        count = 0
        for author_id in queryset.values_list('author_id', flat=True).distinct():
            if not author_id:
                continue
            ban, created = BlogBan.objects.get_or_create(user_id=author_id, active=True, defaults={'until': until})
            if not created:
                # extend ban if shorter
                if not ban.until or ban.until < until:
                    ban.until = until
                    ban.save(update_fields=['until'])
            count += 1
        self.message_user(request, f"Zbanowano/odświeżono bany dla użytkowników: {count}")
    ban_authors_24h.short_description = "Zbanuj autorów (24h)"

    def ban_ips_24h(self, request, queryset):
        until = timezone.now() + timedelta(hours=24)
        count = 0
        for ip in queryset.values_list('ip_address', flat=True).distinct():
            if not ip:
                continue
            ban, created = BlogBan.objects.get_or_create(ip_address=ip, active=True, defaults={'until': until})
            if not created:
                if not ban.until or ban.until < until:
                    ban.until = until
                    ban.save(update_fields=['until'])
            count += 1
        self.message_user(request, f"Zbanowano/odświeżono bany dla IP: {count}")
    ban_ips_24h.short_description = "Zbanuj IP (24h)"


@admin.register(BlogBan)
class BlogBanAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip_address', 'active', 'until', 'reason', 'created_at')
    list_filter = ('active', 'until', 'created_at')
    search_fields = ('user__username', 'ip_address', 'reason')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    actions = ['activate_bans', 'deactivate_bans']

    def activate_bans(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, f"Aktywowano bany: {updated}")
    activate_bans.short_description = "Aktywuj bany"

    def deactivate_bans(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, f"Dezaktywowano bany: {updated}")
    deactivate_bans.short_description = "Dezaktywuj bany"
