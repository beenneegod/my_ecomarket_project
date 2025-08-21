from django import template
from django.templatetags.static import static
from store.utils.images import get_or_generate_variant
from django.conf import settings

register = template.Library()


@register.simple_tag
def product_image(product, key='card'):
    """
    Returns URL for optimized product image variant or a category/default fallback.
    key: 'card' | 'thumb' | 'detail'
    """
    # Try product image
    if getattr(product, 'image', None):
        if getattr(settings, 'IMAGE_VARIANTS_ENABLED', True) is False:
            # Serve original directly
            if hasattr(product.image, 'url'):
                return product.image.url
        url = get_or_generate_variant(product.image, key)
        if url:
            return url
    # Try category default image from static per category slug
    if getattr(product, 'category', None) and getattr(product.category, 'slug', None):
        candidate = f"img/categories/{product.category.slug}.webp"
        # static always returns a URL; we assume build has this file if provided
        return static(candidate)
    # Global fallback
    return static('img/no_image.png')
