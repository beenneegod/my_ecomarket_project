# store/admin.py

from django.contrib import admin
from .models import (Category, Product, Order, OrderItem, Profile, SubscriptionBoxType, UserSubscription, Coupon, UserCoupon, ProductRating)
from import_export.admin import ImportExportModelAdmin
from .admin_resources import CategoryResource, ProductResource
from django.utils.safestring import mark_safe

@admin.register(Category)
class CategoryAdmin(ImportExportModelAdmin):
    resource_class = CategoryResource
    list_display = ('name', 'slug')
    # Автоматически заполнять поле 'slug' на основе значения поля 'name'
    # Удобно при создании новых категорий в админке
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    # Добавляем 'category' в отображаемые поля и поля для редактирования/фильтрации
    resource_class = ProductResource
    list_display = ('name', 'thumbnail_preview', 'category', 'price', 'stock', 'available', 'created_at', 'updated_at')
    list_filter = ('available', 'category', 'created_at', 'updated_at') # Добавляем фильтр по категории
    list_editable = ('price', 'stock', 'available') # Поле category лучше не делать редактируемым в списке
    search_fields = ('name', 'description')
    readonly_fields = ('thumbnail_display', 'created_at', 'updated_at')
    prepopulated_fields = {'slug': ('name',)}


    @admin.display(description='Obrazek') # Или "Изображение" / "Image"
    def thumbnail_preview(self, obj):
        if obj.image:
            return mark_safe(
                f'<img src="{obj.image.url}" width="40" height="40" loading="lazy" '
                f'style="width:40px;height:40px;object-fit:cover;border-radius:4px;" />'
            )
        return "-"
    @admin.display(description='Miniatura')


    @admin.display(description='Aktualny obrazek') # Для страницы редактирования
    def thumbnail_display(self, obj):
        if obj.image:
            return mark_safe(
                f'<img src="{obj.image.url}" width="120" height="120" loading="lazy" '
                f'style="width:120px;height:120px;object-fit:contain;border:1px solid #e5e7eb;border-radius:6px;" />'
            )
        return "Brak obrazka"
class OrderItemInline(admin.TabularInline):
    """
    Встраиваемое отображение элементов заказа на странице заказа.
    TabularInline - отображение в виде таблицы.
    """
    model = OrderItem
    raw_id_fields = ['product'] # Удобный виджет для выбора товара (особенно если их много)
   # readonly_fields = ('',) # Цену элемента заказа менять не должны
    extra = 0 # Не показывать пустые формы для добавления новых OrderItem по умолчанию

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # Отображаем больше информации в списке
    list_display = ('id', 'get_full_name', 'email', 'city', 'created_at', 'paid')
    list_filter = ('paid', 'created_at', 'updated_at')
    search_fields = ('id', 'first_name', 'last_name', 'email', 'stripe_id') # Добавляем поиск по имени/фамилии
    # Делаем поля адреса и пользователя только для чтения после создания заказа
    # Поля paid и stripe_id тоже обычно не меняют вручную
    readonly_fields = ('user', 'first_name', 'last_name', 'email',
                     'address_line_1', 'address_line_2', 'postal_code',
                     'city', 'country', 'created_at', 'updated_at', 'stripe_id',
                     'get_total_cost_display')
    inlines = [OrderItemInline]

    # Группируем поля на странице редактирования для лучшего вида
    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'user', 'paid', 'stripe_id', 'created_at', 'updated_at', 'get_total_cost_display')
        }),
        ('Контактная информация и адрес доставки', {
            'fields': ('first_name', 'last_name', 'email', 'address_line_1', 'address_line_2', 'postal_code', 'city', 'country')
        }),
    )

    # Переопределяем метод, чтобы id тоже был только для чтения
    def get_readonly_fields(self, request, obj=None):
        # Получаем базовый набор readonly полей
        readonly_fields = set(super().get_readonly_fields(request, obj))
        # Всегда добавляем 'id' в readonly
        readonly_fields.add('id')
        return list(readonly_fields)

    # Запрещаем добавление заказов через админку (они должны создаваться через оплату)
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj and obj.paid:
            return False # Нельзя удалять оплаченный заказ
        return super().has_delete_permission(request, obj)

    # Используем существующий метод get_full_name из модели для отображения
    @admin.display(description='Klient')
    def get_full_name(self, obj):
        if obj.user:
             # Если есть пользователь, берем его полное имя или username
             return obj.user.get_full_name() or obj.user.username
        # Если пользователя нет (анонимный заказ), берем из полей заказа
        return f"{obj.first_name} {obj.last_name}" if obj.first_name else '(Anonymous)'


    @admin.display(description='Suma zamówienia')
    def get_total_cost_display(self, obj):
        return f"{obj.get_total_cost()} PLN"


@admin.register(ProductRating)
class ProductRatingAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "value", "created_at")
    list_filter = ("value", "created_at")
    search_fields = ("product__name", "user__username")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'avatar_preview', 'bio_short', 'stripe_customer_id')
    search_fields = ('user__username', 'user__email', 'stripe_customer_id')
    readonly_fields = ('user', 'avatar_display', 'stripe_customer_id')

    @admin.display(description='Krótkie Bio')
    def bio_short(self, obj):
        if obj.bio:
            return obj.bio[:50] + '...' if len(obj.bio) > 50 else obj.bio
        return "-"
    
    @admin.display(description='Awatar') # Или "Аватар" / "Avatar"
    def avatar_preview(self, obj):
        if obj.avatar and hasattr(obj.avatar, 'url') and obj.avatar.url:
            return mark_safe(f'<img src="{obj.avatar.url}" style="max-height: 40px; max-width: 40px; border-radius: 50%;" />')
        return "-"
    avatar_preview.short_description = 'Miniatura'
    
    @admin.display(description='Aktualny awatar')
    def avatar_display(self, obj):
        if obj.avatar and hasattr(obj.avatar, 'url') and obj.avatar.url:
            return mark_safe(f'<img src="{obj.avatar.url}" style="max-height: 150px; max-width: 150px; border-radius: 10px;" />')
        return "Brak awatara"


@admin.register(SubscriptionBoxType)
class SubscriptionBoxTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'billing_period', 'is_active', 'stripe_price_id')
    list_filter = ('is_active', 'billing_period')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('price', 'is_active', 'stripe_price_id')

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'box_type', 'status', 'start_date', 'current_period_end', 'stripe_subscription_id', 'get_stripe_customer_id_from_profile') # Изменено
    list_filter = ('status', 'box_type', 'start_date', 'current_period_end')
    search_fields = ('user__username', 'box_type__name', 'stripe_subscription_id', 'user__profile__stripe_customer_id') 
    list_select_related = ('user', 'box_type', 'user__profile')
    readonly_fields = ('user', 'box_type', 'start_date', 'stripe_subscription_id', 
                       'current_period_start', 'current_period_end', 'cancel_at_period_end',
                       'get_stripe_customer_id_from_profile') 

    @admin.display(description='ID klienta Stripe (z Profilu)') # Описание для колонки
    def get_stripe_customer_id_from_profile(self, obj):
        if obj.user and hasattr(obj.user, 'profile') and obj.user.profile.stripe_customer_id:
            return obj.user.profile.stripe_customer_id
        return "-"
    # get_stripe_customer_id_from_profile.short_description = 'Stripe Customer ID (z Profilu)' # Альтернативный способ задания имени колонки

    def get_queryset(self, request):
        # Оптимизируем запрос, чтобы сразу подгружать связанные профили
        return super().get_queryset(request).select_related('user__profile')

    def get_readonly_fields(self, request, obj=None):
        # Получаем базовый набор readonly полей из определения класса
        base_readonly_fields = list(self.readonly_fields)
        if obj: # При редактировании существующего объекта
            # Статус тоже лучше менять через логику, а не вручную
            # Убедимся, что 'status' не дублируется, если он уже есть в self.readonly_fields
            if 'status' not in base_readonly_fields:
                 base_readonly_fields.append('status')
        return base_readonly_fields

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount', 'valid_from', 'valid_to', 'active')
    list_filter = ('active', 'valid_from', 'valid_to')
    search_fields = ('code',)
    ordering = ('-valid_from',)
    fieldsets = (
        (None, {
            'fields': ('code', 'discount', 'valid_from', 'valid_to', 'active')
        }),
    )

@admin.action(description="Отметить как использованные")
def mark_as_used(modeladmin, request, queryset):
    queryset.update(is_used=True)

@admin.action(description="Отметить как неиспользованные")
def mark_as_unused(modeladmin, request, queryset):
    queryset.update(is_used=False)

@admin.action(description="Удалить все неиспользованные и истекшие купоны")
def delete_expired_unused_coupons(modeladmin, request, queryset):
    from django.utils import timezone
    now = timezone.now()
    count, _ = queryset.filter(is_used=False, coupon__valid_to__lt=now).delete()
    modeladmin.message_user(request, f"Удалено {count} неиспользованных истекших купонов.")

@admin.action(description="Экспортировать выбранные купоны в CSV")
def export_to_csv(modeladmin, request, queryset):
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=user_coupons.csv'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Пользователь', 'Купон', 'Код', 'Скидка', 'Использован', 'Дата выдачи', 'Источник'])
    for uc in queryset:
        writer.writerow([
            uc.id, uc.user.username, uc.coupon.id, uc.coupon.code, uc.coupon.discount, uc.is_used, uc.awarded_at, getattr(uc.challenge_source, 'title', '')
        ])
    return response

@admin.action(description="Отправить email-напоминание о неиспользованных купонах")
def send_coupon_reminder(modeladmin, request, queryset):
    from common.mail import send_email
    for uc in queryset.filter(is_used=False):
        send_email(
            subject="У вас есть неиспользованный купон!",
            to=[uc.user.email],
            text=f"Здравствуйте, {uc.user.username}! У вас есть купон {uc.coupon.code} на скидку {uc.coupon.discount}%. Не забудьте использовать его до {uc.coupon.valid_to.strftime('%d.%m.%Y')}!",
            fail_silently=True,
        )
    modeladmin.message_user(request, f"Отправлено {queryset.filter(is_used=False).count()} напоминаний.")

@admin.action(description="Выдать выбранный купон выбранным пользователям")
def assign_coupon_to_users(modeladmin, request, queryset):
    from django.contrib.auth import get_user_model
    from django import forms
    from django.shortcuts import render
    from .models import Coupon, UserCoupon
    class CouponChoiceForm(forms.Form):
        coupon = forms.ModelChoiceField(queryset=Coupon.objects.filter(active=True), label="Купон для выдачи")
    if 'apply' in request.POST:
        form = CouponChoiceForm(request.POST)
        if form.is_valid():
            coupon = form.cleaned_data['coupon']
            count = 0
            for user_coupon in queryset:
                user = user_coupon.user
                # Не выдаём дубликаты
                if not UserCoupon.objects.filter(user=user, coupon=coupon).exists():
                    UserCoupon.objects.create(user=user, coupon=coupon)
                    count += 1
            modeladmin.message_user(request, f"Выдано {count} купонов.")
            return
    else:
        form = CouponChoiceForm()
    return render(request, 'admin/assign_coupon.html', context={'form': form, 'queryset': queryset})

@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'user', 'is_used', 'awarded_at', 'challenge_source', 'colored_status')
    list_filter = ('is_used', 'awarded_at', 'coupon', 'challenge_source')
    search_fields = ('coupon__code', 'user__username', 'user__email')
    autocomplete_fields = ['user', 'coupon', 'challenge_source']
    readonly_fields = ('awarded_at',)
    ordering = ('-awarded_at',)
    actions = [mark_as_used, mark_as_unused, delete_expired_unused_coupons, export_to_csv, send_coupon_reminder, assign_coupon_to_users]
    fieldsets = (
        (None, {
            'fields': ('user', 'coupon', 'is_used', 'awarded_at', 'challenge_source')
        }),
    )

    def colored_status(self, obj):
        color = '#28a745' if not obj.is_used else '#6c757d'
        label = 'Активен' if not obj.is_used else 'Использован'
        return mark_safe(f'<span style="color: {color}; font-weight: bold;">{label}</span>')
    colored_status.short_description = 'Статус'