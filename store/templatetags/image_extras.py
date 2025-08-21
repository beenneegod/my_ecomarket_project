from django import template
from django.templatetags.static import static
from store.utils.images import get_or_generate_variant
from django.utils.html import escape

register = template.Library()


@register.simple_tag
def product_image(product, key='card'):
    """
    Returns URL for optimized product image variant or a category/default fallback.
    key: 'card' | 'thumb' | 'detail'
    """
    # Try product image
    if getattr(product, 'image', None):
        url = get_or_generate_variant(product.image, key)
        if url:
            return url
        # Fallback to original image URL if variant failed to generate
        if getattr(product.image, 'url', None):
            return product.image.url
    # Try category default image from static per category slug
    if getattr(product, 'category', None) and getattr(product.category, 'slug', None):
        candidate = f"img/categories/{product.category.slug}.webp"
        # static always returns a URL; we assume build has this file if provided
        return static(candidate)
    # Global fallback
    return static('img/no_image.png')
