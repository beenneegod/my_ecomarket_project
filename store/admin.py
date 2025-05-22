# store/admin.py

from django.contrib import admin
from .models import Category, Product, Order, OrderItem, Profile
from import_export.admin import ImportExportModelAdmin
from .admin_resources import CategoryResource, ProductResource


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    resource_class = CategoryResource
    list_display = ('name', 'slug')
    # Автоматически заполнять поле 'slug' на основе значения поля 'name'
    # Удобно при создании новых категорий в админке
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    # Добавляем 'category' в отображаемые поля и поля для редактирования/фильтрации
    resource_class = ProductResource
    list_display = ('name', 'category', 'price', 'stock', 'available', 'created_at', 'updated_at')
    list_filter = ('available', 'category', 'created_at', 'updated_at') # Добавляем фильтр по категории
    list_editable = ('price', 'stock', 'available') # Поле category лучше не делать редактируемым в списке
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    prepopulated_fields = {'slug': ('name',)}

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

    # Опционально: Запрещаем удаление оплаченных заказов
    # def has_delete_permission(self, request, obj=None):
    #     if obj and obj.paid:
    #         return False # Нельзя удалять оплаченный заказ
    #     return super().has_delete_permission(request, obj)

    # Используем существующий метод get_full_name из модели для отображения
    @admin.display(description='Клиент')
    def get_full_name(self, obj):
        if obj.user:
             # Если есть пользователь, берем его полное имя или username
             return obj.user.get_full_name() or obj.user.username
        # Если пользователя нет (анонимный заказ), берем из полей заказа
        return f"{obj.first_name} {obj.last_name}" if obj.first_name else '(Анонимно)'


    @admin.display(description='Общая стоимость')
    def get_total_cost_display(self, obj):
        return f"{obj.get_total_cost()} PLN"


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'avatar', 'bio_short')
    search_fields = ('user__username', 'user__email')

    @admin.display(description='Krótkie Bio')
    def bio_short(self, obj):
        if obj.bio:
            return obj.bio[:50] + '...' if len(obj.bio) > 50 else obj.bio
        return "-"
# Базовая регистрация OrderItem (не обязательно, т.к. он встроен в Order)
# Если хотите видеть OrderItem отдельно:
# @admin.register(OrderItem)
# class OrderItemAdmin(admin.ModelAdmin):
#     list_display = ('order', 'product', 'price', 'quantity')
#     list_filter = ('order__created_at',) # Фильтр по дате связанного заказа
#     search_fields = ('order__id', 'product__name')