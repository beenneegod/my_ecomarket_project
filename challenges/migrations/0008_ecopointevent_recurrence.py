from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('challenges', '0007_challenge_reward_coupon'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='challenge',
            name='recurrence_type',
            field=models.CharField(
                choices=[('none', 'Bez powtarzania'), ('weekly', 'Co tydzień'), ('monthly', 'Co miesiąc')],
                default='none',
                max_length=10,
                verbose_name='Powtarzanie (dla szablonu)'
            ),
        ),
        migrations.CreateModel(
            name='EcoPointEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.PositiveIntegerField(verbose_name='Punkty')),
                ('source', models.CharField(choices=[('challenge', 'Wyzwanie')], default='challenge', max_length=20, verbose_name='Źródło')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('challenge', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='point_events', to='challenges.challenge')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='eco_point_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Zdarzenie punktowe',
                'verbose_name_plural': 'Zdarzenia punktowe',
                'ordering': ['-created_at'],
            },
        ),
    ]
