from django.core.management.base import BaseCommand
from challenges.services.recurrence import generate_recurrent_challenges


class Command(BaseCommand):
    help = "Tworzy kolejne instancje wyzwań na podstawie szablonów z ustawioną powtarzalnością."

    def handle(self, *args, **options):
        summary = generate_recurrent_challenges()
        self.stdout.write(self.style.SUCCESS(f"Utworzono instancji: {summary['created']}"))
