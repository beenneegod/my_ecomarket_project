from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("challenges", "0009_challenge_max_future_instances"),
    ]

    operations = [
        migrations.AddField(
            model_name="userchallengeparticipation",
            name="proof_file",
            field=models.FileField(blank=True, null=True, upload_to="challenge_proofs/", verbose_name="Dowód (zdjęcie/wideo)"),
        ),
    ]
