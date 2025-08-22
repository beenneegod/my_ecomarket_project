from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("challenges", "0011_alter_challenge_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="userchallengeparticipation",
            name="review_notes",
            field=models.TextField(blank=True, null=True, verbose_name="Uwagi moderatora"),
        ),
    ]
