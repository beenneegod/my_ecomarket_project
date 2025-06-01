# blog/serializers.py
from rest_framework import serializers
from .models import Post
from django.contrib.auth import get_user_model
# from django.utils.text import slugify # Для генерации слага # F401 unused import

User = get_user_model()

class PostCreateSerializer(serializers.ModelSerializer):
    # Мы можем сделать поле author необязательным для входящих данных,
    # так как мы установим автора программно на основе API-ключа или токена.
    # Или же мы можем ожидать ID автора, если это будет определенный "системный" пользователь.
    # Для простоты, предположим, что автор будет назначен во view.
    # Поле slug также будет генерироваться автоматически.

    # title и body будут основными полями, которые мы ожидаем от API-запроса.
    # image может быть опциональным.

    class Meta:
        model = Post
        fields = ['title', 'body', 'image', 'status', 'published_at'] # Поля, которые можно передать через API
        # Поля 'slug' и 'author' будут установлены во view
        read_only_fields = ('slug', 'author', 'created_at', 'updated_at')

    def validate_title(self, value):
        # Можно добавить кастомную валидацию, если нужно
        if len(value) < 10:
            raise serializers.ValidationError("Заголовок поста должен быть длиннее 10 символов.")
        return value

    # Мы не будем здесь переопределять create(), так как основная логика
    # по установке автора и генерации слага будет во view API.
    # Или можно это сделать здесь, если передавать request в контекст сериализатора.