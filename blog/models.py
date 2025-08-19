from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.core.files.base import ContentFile
from io import BytesIO
from PIL import Image
from store.models import get_product_image_storage_instance
class Post(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_posts'
    )
    body = models.TextField()
    image = models.ImageField(
        upload_to='blog_images/%Y/%m/%d/',
        blank=True,
        null=True,
        storage=get_product_image_storage_instance()
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft'
    )

    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['-published_at']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('blog:post_detail', args=[self.slug])

class Comment(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_comments'
    )
    body = models.TextField(max_length=500)
    image = models.ImageField(
        upload_to='blog_comments/%Y/%m/%d/',
        blank=True, # Поле необязательное
        null=True,  # Разрешаем NULL в БД
        verbose_name="Obrazek",
        storage=get_product_image_storage_instance()
    )
    image_thumb = models.ImageField(
        upload_to='blog_comments/thumbs/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name="Miniatura",
        storage=get_product_image_storage_instance()
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='moderated_blog_comments')
    remove_reason = models.CharField(max_length=250, blank=True, default='')

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'Comment by {self.author} on {self.post}'

    def save(self, *args, **kwargs):
        # Save first to ensure self.image has a file path
        super_save = super().save
        creating = self.pk is None
        super_save(*args, **kwargs)
        # Generate thumbnail if needed
        if self.image and (not self.image_thumb or creating):
            try:
                self._generate_thumbnail()
            except Exception:
                # Silently ignore thumbnail failures
                return

    def _generate_thumbnail(self, max_size=(600, 600), quality=82):
        if not self.image:
            return
        # Open original image
        self.image.open('rb')
        with BytesIO(self.image.read()) as buf:
            img = Image.open(buf)
            # Convert to RGB to ensure consistent JPEG output
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            # Resize in-place preserving aspect ratio
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            out = BytesIO()
            img.save(out, format='JPEG', quality=quality, optimize=True, progressive=True)
            out.seek(0)
            # Build name
            base = (self.image.name.rsplit('/', 1)[-1]).rsplit('.', 1)[0]
            thumb_name = f"{base}_thumb.jpg"
            # Store in the configured storage path using image_thumb's upload_to
            # image_thumb.save handles storage and naming within upload_to dir
            content = ContentFile(out.read())
            # Ensure directory structure by re-calling save on model
            self.image_thumb.save(thumb_name, content, save=False)
            super().save(update_fields=['image_thumb'])


class CommentRating(models.Model):
    VALUE_CHOICES = [
        (1, '1 gwiazdka'), (2, '2 gwiazdki'), (3, '3 gwiazki'), (4, '4 gwiazdki'), (5, '5 gwiazdek')
    ]
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comment_ratings')
    value = models.PositiveSmallIntegerField(choices=VALUE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('comment', 'user')
        indexes = [
            models.Index(fields=['comment', 'user']),
        ]

    def __str__(self):
        return f'Rating {self.value} by {self.user} on comment {self.comment_id}'


class BlogBan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name='blog_bans')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    reason = models.CharField(max_length=250, blank=True, default='')
    until = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['active']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['user']),
        ]

    def __str__(self) -> str:
        who = self.user or self.ip_address or '—'
        return f"Ban({who}) active={self.active} until={self.until}"
