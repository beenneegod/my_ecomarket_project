from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from store.models import Product, Category, SubscriptionBoxType
from blog.models import Post


class ProductSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.8

    def items(self):
        return Product.objects.filter(available=True)

    def location(self, obj: Product):
        return obj.get_absolute_url()

    def lastmod(self, obj: Product):
        return obj.updated_at or obj.created_at


class CategorySitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        return Category.objects.all()

    def location(self, obj: Category):
        return obj.get_absolute_url()


class BlogPostSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.5

    def items(self):
        return Post.objects.filter(status='published')

    def location(self, obj: Post):
        return obj.get_absolute_url()

    def lastmod(self, obj: Post):
        return obj.updated_at or obj.published_at


class StaticViewSitemap(Sitemap):
    priority = 0.9
    changefreq = 'daily'

    def items(self):
        return ['homepage',]

    def location(self, item):
        return reverse(item)


class SubscriptionBoxSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        return SubscriptionBoxType.objects.filter(is_active=True)

    def location(self, obj: SubscriptionBoxType):
        return obj.get_absolute_url()
