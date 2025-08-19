from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from blog.models import Comment


class Command(BaseCommand):
    help = "Generate thumbnails for blog comment images (like chat thumbs)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            '--force', action='store_true', default=False,
            help='Regenerate thumbnails even if already present.'
        )
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Limit the number of processed comments (0 = no limit).'
        )
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='Show what would be done without saving changes.'
        )

    def handle(self, *args, **options):
        force = bool(options.get('force'))
        limit = int(options.get('limit') or 0)
        dry_run = bool(options.get('dry_run'))

        qs = Comment.objects.filter(image__isnull=False)
        if not force:
            qs = qs.filter(image_thumb__isnull=True)

        total = qs.count()
        if limit > 0:
            total = min(total, limit)
        self.stdout.write(self.style.NOTICE(
            f"Processing up to {total} comment(s) (force={force}, dry_run={dry_run})"
        ))

        processed = 0
        created = 0
        skipped = 0
        errors = 0

        for comment in qs.iterator(chunk_size=100):
            if limit and processed >= limit:
                break
            processed += 1
            try:
                if not force and comment.image_thumb:
                    skipped += 1
                    continue
                if dry_run:
                    # Simulate work
                    created += 1
                    self.stdout.write(f"[DRY] Would generate thumb for comment #{comment.id}")
                    continue
                with transaction.atomic():
                    # Use model helper to generate and persist
                    comment._generate_thumbnail()
                    created += 1
                    self.stdout.write(f"OK  Generated thumb for comment #{comment.id}")
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.WARNING(
                    f"ERR Failed for comment #{comment.id}: {exc}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"Done. processed={processed}, created={created}, skipped={skipped}, errors={errors}"
        ))
