from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_chatroom_owner_message_is_removed_messageattachment_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='reply_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='replies', to='chat.message', verbose_name='Odpowiedź na'),
        ),
    ]
