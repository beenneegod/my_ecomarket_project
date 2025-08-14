from django.core.management.base import BaseCommand
from places.models import EcoPlace

class Command(BaseCommand):
    help = "Usuwa miejsca bez nazwy (np. 'Bez nazwy')."

    def handle(self, *args, **options):
        qs = EcoPlace.objects.filter(name__iexact="Bez nazwy")
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Usunięto rekordów: {count}"))
