from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, CharWidget # Добавляем CharWidget
from .models import Product, Category
#from django.core.files.base import ContentFile # Для работы с файлами
#import os
#from django.conf import settings


class CategoryResource(resources.ModelResource):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug') # Укажите поля для импорта/экспорта
        # exclude = ('некие_поля_для_исключения',)
        import_id_fields = ('id',) # По какому полю искать существующие записи для обновления (можно 'slug' или 'name')
        skip_unchanged = True # Пропускать строки, которые не изменились
        report_skipped = True # Сообщать о пропущенных строках

class ProductResource(resources.ModelResource):
    category = fields.Field(
        column_name='category_name',
        attribute='category',
        widget=ForeignKeyWidget(Category, 'name')
    )
    # Для поля image будем использовать CharWidget, чтобы прочитать путь как строку
    image_path = fields.Field(
        column_name='image', # Название колонки в CSV
        attribute='image',   # Атрибут модели Product
        widget=CharWidget()  # Читаем как строку
    )

    class Meta:
        model = Product
        # Убедимся, что поле 'image' есть в fields, чтобы оно читалось из CSV
        fields = ('id', 'name', 'slug', 'category', 'description', 'price', 'stock', 'available', 'image')
        export_order = fields
        import_id_fields = ('id',)
        skip_unchanged = True
        report_skipped = True
        # Мы не хотим, чтобы import-export пытался сам создать FileField из строки пути напрямую,
        # поэтому мы перехватим это значение и обработаем.
        # Можно также добавить use_transactions = True для атомарности импорта.
        use_transactions = True
        # Если у вас есть поле ImageField, его прямая загрузка через CSV/Excel сложна.
        # Обычно путь к изображению (относительный или URL) указывают в файле,
        # а затем пишут кастомную логику для загрузки изображения по этому пути
        # (например, переопределяя метод after_import в ModelAdmin).
        # Для простоты, можно пока импортировать без изображений или только путь,
        # а изображения загружать вручную.
        # exclude = ('image',) # Если хотите исключить поле image из прямого импорта

    # Пример кастомной обработки поля image (если в CSV есть URL изображения)
    # def dehydrate_image(self, product):
    #     if product.image:
    #         return product.image.url
    #     return ""

    def before_import_row(self, row, **kwargs):
        """
        Вызывается перед тем, как данные из 'row' будут использованы для создания
        или обновления экземпляра модели. 'row' - это словарь.
        kwargs может содержать 'file_name', 'user' и др.
        """
        image_path_from_csv = row.get('image') # Получаем значение из колонки 'image'

        if image_path_from_csv:
            # Django ImageField может принимать относительный путь (относительно MEDIA_ROOT),
            # если файл уже существует по этому пути.
            # Убедимся, что это просто строка пути, которую Django сможет обработать.
            # Ничего специально делать не нужно, если Django настроен правильно
            # и файлы лежат в MEDIA_ROOT/import_temp/your_image.jpg,
            # а в CSV указан "import_temp/your_image.jpg".
            # Django сам скопирует файл при сохранении объекта Product в
            # его upload_to директорию.
            # Просто оставляем значение image_path_from_csv в row['image'].
            pass
        else:
            # Если путь не указан, можно установить None или пустую строку,
            # в зависимости от того, как ImageField обрабатывает это
            row['image'] = None # Или ''

        # Убедимся, что price и stock это корректные числа, если они приходят как строки
        # (хотя import-export обычно справляется с конвертацией, если поля Decimal/Integer)
        if 'price' in row and row['price']:
            try:
                row['price'] = str(row['price']).replace(',', '.') # Заменяем запятую на точку для Decimal
            except Exception:
                pass # Оставляем как есть, если конвертация не удалась, import-export выдаст ошибку позже
        
        if 'stock' in row and row['stock'] == '': # Если сток пустой, делаем его 0
            row['stock'] = 0