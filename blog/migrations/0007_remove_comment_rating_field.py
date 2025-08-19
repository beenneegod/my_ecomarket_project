from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('blog', '0006_rename_blog_commen_comment_8b9849_idx_blog_commen_comment_d29877_idx'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='comment',
            name='rating',
        ),
    ]
