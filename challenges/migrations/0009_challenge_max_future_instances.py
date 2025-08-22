from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenges', '0008_ecopointevent_recurrence'),
    ]

    operations = [
        migrations.AddField(
            model_name='challenge',
            name='max_future_instances',
            field=models.PositiveSmallIntegerField(default=1, verbose_name='Maks. aktywnych/nadchodzących instancji (dla szablonu)'),
        ),
    ]
