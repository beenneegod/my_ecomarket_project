import io
import os
from dataclasses import dataclass
from typing import Optional, Tuple

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import hashlib
from PIL import Image


@dataclass(frozen=True)
class Variant:
    size: Tuple[int, int]
    mode: str  # 'cover' or 'contain'


VARIANTS = {
    'card': Variant((400, 300), 'cover'),
    'thumb': Variant((200, 200), 'cover'),
    'detail': Variant((1000, 750), 'contain'),
}


def _variant_path(original_name: str, key: str) -> str:
    base, _ = os.path.splitext(original_name)
    digest = hashlib.md5(original_name.encode('utf-8')).hexdigest()[:8]
    return f"products/variants/{key}/{os.path.basename(base)}-{digest}.webp"


def _resize(image: Image.Image, target: Variant) -> Image.Image:
    img = image.convert('RGB')
    tw, th = target.size
    if target.mode == 'cover':
        img.thumbnail((tw, th), Image.Resampling.LANCZOS)
        # pad to exact canvas
        bg = Image.new('RGB', (tw, th), (255, 255, 255))
        # center
        x = (tw - img.width) // 2
        y = (th - img.height) // 2
        bg.paste(img, (x, y))
        return bg
    else:  # contain
        img.thumbnail((tw, th), Image.Resampling.LANCZOS)
        bg = Image.new('RGB', (tw, th), (255, 255, 255))
        x = (tw - img.width) // 2
        y = (th - img.height) // 2
        bg.paste(img, (x, y))
        return bg


def get_or_generate_variant(image_field, key: str) -> Optional[str]:
    """
    Returns URL to a generated WebP variant for the given ImageField.
    Generates and stores once using default_storage.
    """
    if not image_field:
        return None
    var = VARIANTS.get(key)
    if not var:
        return getattr(image_field, 'url', None)

    src_name = image_field.name
    dst_name = _variant_path(src_name, key)
    if default_storage.exists(dst_name):
        return default_storage.url(dst_name)

    try:
        with image_field.open('rb') as f:
            im = Image.open(f)
            out = _resize(im, var)
            buf = io.BytesIO()
            out.save(buf, format='WEBP', quality=80, method=6)
            content = ContentFile(buf.getvalue())
            default_storage.save(dst_name, content)
            return default_storage.url(dst_name)
    except Exception:
        # Fallback to original URL
        return getattr(image_field, 'url', None)
