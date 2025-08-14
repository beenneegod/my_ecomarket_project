from django.db import models
from django.conf import settings


class ChatRoom(models.Model):
    name = models.CharField(max_length=120, verbose_name='Nazwa')
    topic = models.CharField(max_length=200, blank=True, verbose_name='Temat')
    is_private = models.BooleanField(default=False, verbose_name='Prywatny')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_chat_rooms', verbose_name='Właściciel')
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='chat_rooms', blank=True, verbose_name='Uczestnicy')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pokój czatu'
        verbose_name_plural = 'Pokoje czatu'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.name


class Message(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_messages')
    text = models.TextField()
    is_removed = models.BooleanField(default=False, verbose_name='Usunięta')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Wiadomość'
        verbose_name_plural = 'Wiadomości'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.user}: {self.text[:30]}"


class MessageAttachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='attachments', verbose_name='Wiadomość')
    file = models.FileField(upload_to='chat_attachments/%Y/%m/', verbose_name='Plik')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Załącznik wiadomości'
        verbose_name_plural = 'Załączniki wiadomości'

    def __str__(self) -> str:
        return f"Załącznik {self.id} do wiadomości {self.message_id}"


class ChatInvite(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Oczekujące'),
        ('accepted', 'Zaakceptowane'),
        ('declined', 'Odrzucone'),
    )
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='invites', verbose_name='Pokój')
    inviter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_chat_invites', verbose_name='Zapraszający')
    invitee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_chat_invites', verbose_name='Zaproszony')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name='Status')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Zaproszenie do pokoju'
        verbose_name_plural = 'Zaproszenia do pokoi'
        unique_together = ('room', 'invitee', 'status')

    def __str__(self) -> str:
        return f"{self.inviter} -> {self.invitee} ({self.room}) [{self.status}]"
