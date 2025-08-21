from django.core.management.base import BaseCommand
from django.db.models import Q
from store.models import Product
from store.utils.images import get_or_generate_variant

class Command(BaseCommand):
    help = "Generate and upload missing WebP image variants for all products (card, thumb, detail)."

    def add_arguments(self, parser):
        parser.add_argument('--only', choices=['card','thumb','detail'], help='Generate only this variant')
        parser.add_argument('--limit', type=int, help='Limit number of products processed')
        parser.add_argument('--dry-run', action='store_true', help='Do not write files, just report (not supported yet)')

    def handle(self, *args, **options):
        qs = Product.objects.filter(~Q(image=''), image__isnull=False)
        if options.get('limit'):
            qs = qs[: options['limit']]
        count = 0
        keys = [options['only']] if options.get('only') else ['card','thumb','detail']
        for p in qs.iterator():
            for k in keys:
                url = get_or_generate_variant(p.image, k)
                if url:
                    self.stdout.write(self.style.SUCCESS(f"OK {p.slug} [{k}] -> {url}"))
                else:
                    self.stdout.write(self.style.WARNING(f"SKIP {p.slug} [{k}] (no image/url)"))
            count += 1
        self.stdout.write(self.style.NOTICE(f"Processed products: {count}"))
