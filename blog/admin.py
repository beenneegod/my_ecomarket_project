from django.contrib import admin
from .models import Post, Comment

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
    list_display = ('author', 'post', 'created_at', 'active')
    list_filter = ('active', 'created_at', 'updated_at', 'author')
    search_fields = ('author__username', 'post__title', 'body')
    actions = ['approve_comments', 'disapprove_comments']

    def approve_comments(self, request, queryset):
        queryset.update(active=True)
    approve_comments.short_description = "Zatwierdź wybrane komentarze"

    def disapprove_comments(self, request, queryset):
        queryset.update(active=False)
    disapprove_comments.short_description = "Odrzuć wybrane komentarze"
