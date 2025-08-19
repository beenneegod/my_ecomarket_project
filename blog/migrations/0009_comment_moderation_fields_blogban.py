from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0008_comment_image_thumb'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='comment',
            name='ip_address',
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name='IP'),
        ),
        migrations.AddField(
            model_name='comment',
            name='remove_reason',
            field=models.CharField(blank=True, default='', max_length=250),
        ),
        migrations.AddField(
            model_name='comment',
            name='removed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='comment',
            name='removed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moderated_blog_comments', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='BlogBan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('reason', models.CharField(blank=True, default='', max_length=250)),
                ('until', models.DateTimeField(blank=True, null=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='blog_bans', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='blogban',
            index=models.Index(fields=['active'], name='blog_ban_active_idx'),
        ),
        migrations.AddIndex(
            model_name='blogban',
            index=models.Index(fields=['ip_address'], name='blog_ban_ip_idx'),
        ),
        migrations.AddIndex(
            model_name='blogban',
            index=models.Index(fields=['user'], name='blog_ban_user_idx'),
        ),
    ]
