from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('blog', '0003_alter_comment_image_alter_post_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='comment',
            name='rating',
            field=models.PositiveSmallIntegerField(
                verbose_name='Ocena',
                choices=[(1, '1 gwiazdka'), (2, '2 gwiazdki'), (3, '3 gwiazdki'), (4, '4 gwiazdki'), (5, '5 gwiazdek')],
                default=5,
                help_text='Oceń komentarz od 1 do 5 gwiazdek.'
            ),
        ),
    ]
