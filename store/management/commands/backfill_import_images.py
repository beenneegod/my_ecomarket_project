import os
import io
from urllib.parse import urlparse
from urllib.request import urlopen

from django.core.files.base import File, ContentFile
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import Q

from store.models import Product


class Command(BaseCommand):
    help = "Backfill product images that still reference import_temp by uploading local/URL sources to the configured storage and updating Product.image."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Max number of products to process (0 = no limit)")
        parser.add_argument("--slug", type=str, default=None, help="Process only a specific product slug")
        parser.add_argument("--dry-run", action="store_true", help="Do not write changes, only show what would be done")

    def handle(self, *args, **options):
        limit = options.get("limit") or 0
        only_slug = options.get("slug")
        dry_run = options.get("dry_run", False)

        qs = Product.objects.filter(image__isnull=False).exclude(image="")
        # Focus on legacy references like 'import_temp/...'
        qs = qs.filter(Q(image__startswith="import_temp/") | Q(image__startswith="media/import_temp/") | Q(image__endswith="/import_temp") | Q(image__icontains="/import_temp/"))
        if only_slug:
            qs = qs.filter(slug=only_slug)

        total = qs.count()
        if limit and total > limit:
            qs = qs[:limit]

        processed = 0
        fixed = 0
        skipped = 0
        missing = 0

        media_root = getattr(settings, 'MEDIA_ROOT', None)
        import_root = getattr(settings, 'IMPORT_LOCAL_DIR', None)

        self.stdout.write(self.style.NOTICE(f"Scanning {qs.count()} of {total} products for import_temp backfill (dry_run={dry_run})"))

        for p in qs.iterator():
            processed += 1
            src_name = getattr(p.image, 'name', '') or ''
            if not src_name:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"SKIP {p.slug} (no image name)"))
                continue

            # Normalize to bare relative path (strip possible leading 'media/')
            rel = src_name
            if rel.startswith('media/'):
                rel = rel[len('media/'):]

            # Build local candidates
            local_candidates = []
            if media_root:
                local_candidates.append(os.path.join(media_root, rel))
            if import_root:
                # Allow both 'import_temp/foo.jpg' and 'foo.jpg' inside IMPORT_LOCAL_DIR
                local_candidates.append(os.path.join(import_root, rel))
                if rel.startswith('import_temp/'):
                    local_candidates.append(os.path.join(import_root, rel.split('import_temp/', 1)[1]))

            local_path = next((pth for pth in local_candidates if pth and os.path.exists(pth)), None)

            file_bytes = None
            filename = os.path.basename(rel) or 'image.jpg'

            if local_path:
                try:
                    with open(local_path, 'rb') as f:
                        file_bytes = f.read()
                except Exception as e:
                    self.stderr.write(f"ERR {p.slug} failed reading local file {local_path}: {e}")
            else:
                # Try download if the stored name is actually a URL (unlikely for import_temp but safe)
                parsed = urlparse(src_name)
                if parsed.scheme in ('http', 'https'):
                    try:
                        with urlopen(src_name) as resp:
                            file_bytes = resp.read()
                        if parsed.path:
                            filename = os.path.basename(parsed.path) or filename
                    except Exception as e:
                        self.stderr.write(f"ERR {p.slug} failed downloading {src_name}: {e}")

            if not file_bytes:
                missing += 1
                self.stdout.write(self.style.ERROR(f"MISS {p.slug} -> {src_name} (no local/URL source found)"))
                continue

            # Save via ImageField.save so upload_to is respected (products/%Y/%m/%d/)
            if dry_run:
                self.stdout.write(self.style.WARNING(f"DRY {p.slug} would upload {filename} and update Product.image (from {src_name})"))
            else:
                try:
                    buf = io.BytesIO(file_bytes)
                    p.image.save(filename, File(buf), save=True)
                    fixed += 1
                    self.stdout.write(self.style.SUCCESS(f"OK {p.slug} -> {p.image.name}"))
                except Exception as e:
                    self.stderr.write(f"ERR {p.slug} failed saving to storage: {e}")

        self.stdout.write(self.style.NOTICE(f"Done. processed={processed} fixed={fixed} skipped={skipped} missing={missing}"))
