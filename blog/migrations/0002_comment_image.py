# Generated by Django 5.2 on 2025-05-22 09:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='comment',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='blog_comments/%Y/%m/%d/', verbose_name='Obrazek'),
        ),
    ]
