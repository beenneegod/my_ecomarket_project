from django.contrib import admin
from .models import ChatRoom, Message


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'topic', 'is_private', 'created_at')
    search_fields = ('name', 'topic')
    list_filter = ('is_private',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'short_text', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('text', 'user__username', 'room__name')

    def short_text(self, obj):
        return obj.text[:60]
