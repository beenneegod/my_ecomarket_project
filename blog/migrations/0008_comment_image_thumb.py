from django.db import migrations, models
import store.models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0007_remove_comment_rating_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='comment',
            name='image_thumb',
            field=models.ImageField(blank=True, null=True, storage=store.models.get_product_image_storage_instance(), upload_to='blog_comments/thumbs/%Y/%m/%d/', verbose_name='Miniatura'),
        ),
    ]
