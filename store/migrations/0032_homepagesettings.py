from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0031_alter_profile_avatar'),
    ]

    operations = [
        migrations.CreateModel(
            name='HomePageSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hero_image', models.ImageField(blank=True, null=True, upload_to='homepage/', verbose_name='Obrazek hero (góra)')),
                ('hero_image_alt', models.CharField(blank=True, max_length=255, verbose_name='Tekst ALT dla hero')),
                ('box_image', models.ImageField(blank=True, null=True, upload_to='homepage/', verbose_name='Obrazek sekcji box')),
                ('box_image_alt', models.CharField(blank=True, max_length=255, verbose_name='Tekst ALT dla obrazka box')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Ustawienia strony głównej',
                'verbose_name_plural': 'Ustawienia strony głównej',
            },
        ),
    ]
