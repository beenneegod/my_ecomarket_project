from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, CharWidget  # Добавляем CharWidget
from .models import Product, Category
from django.core.files.base import File
from django.conf import settings
import os
import io
from urllib.parse import urlparse
from urllib.request import urlopen


class CategoryResource(resources.ModelResource):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug')  # Укажите поля для импорта/экспорта
        # exclude = ('некие_поля_для_исключения',)
        # Используем slug как уникальный ключ при импорте, чтобы не требовать ID из БД
        import_id_fields = ('slug',)
        skip_unchanged = True  # Пропускать строки, которые не изменились
        report_skipped = True  # Сообщать о пропущенных строках

class ProductResource(resources.ModelResource):
    category = fields.Field(
        column_name='category_name',
        attribute='category',
        widget=ForeignKeyWidget(Category, 'name')
    )
    # Для поля image используем CharWidget, чтобы прочитать путь/URL как строку
    image = fields.Field(
        column_name='image',  # Название колонки в CSV
        attribute='image',    # Атрибут модели Product
        widget=CharWidget()   # Читаем как строку
    )

    class Meta:
        model = Product
        # Убедимся, что поле 'image' есть в fields, чтобы оно читалось из CSV
        fields = ('id', 'name', 'slug', 'category', 'description', 'price', 'stock', 'available', 'image')
        export_order = fields
        # Совпадение по slug позволяет импортировать без ID и выполнять апсерты по слагу
        import_id_fields = ('slug',)
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
        # Нормализуем категорию (поиск идёт по точному имени)
        if 'category_name' in row and row['category_name'] is not None:
            row['category_name'] = str(row['category_name']).strip()

        image_path_from_csv = row.get('image')  # Значение из колонки 'image' (может быть относительный путь или URL)

        if not image_path_from_csv:
            # Если путь не указан, можно установить None или пустую строку,
            # в зависимости от того, как ImageField обрабатывает это
            row['image'] = None # Или ''
        else:
            # Нормализуем строку
            row['image'] = str(image_path_from_csv).strip()

        # Убедимся, что price и stock это корректные числа, если они приходят как строки
        # (хотя import-export обычно справляется с конвертацией, если поля Decimal/Integer)
        if 'price' in row and row['price']:
            try:
                row['price'] = str(row['price']).replace(',', '.') # Заменяем запятую на точку для Decimal
            except:
                pass # Оставляем как есть, если конвертация не удалась, import-export выдаст ошибку позже
        
        if 'stock' in row and row['stock'] == '': # Если сток пустой, делаем его 0
            row['stock'] = 0

    def after_save_instance(self, instance, *args, **kwargs):
        """
        После сохранения товара: если у него указано поле image в виде
        - относительного локального пути (например, import_temp/plik.jpg) и физически файл есть в MEDIA_ROOT,
        - или http(s) URL,
        то открываем источник и сохраняем через ImageField.save(), чтобы файл попал в хранилище
        (в продакшене — в S3, в деве — в локальную папку upload_to).
        """
        # Совместимость с разными версиями django-import-export
        dry_run = kwargs.get('dry_run')
        if dry_run is None and len(args) >= 2:
            # args обычно: (using_transactions, dry_run, ...) — нам нужен второй
            dry_run = args[1]

        if dry_run:
            return

        img_name = getattr(instance.image, 'name', None)
        if not img_name:
            return

        # Если уже сохранено под upload_to (products/YYYY/MM/DD/...), ничего не делаем
        if img_name.startswith('products/'):
            return

        source = img_name
        # 1) Попытка локального файла под MEDIA_ROOT
        local_path = os.path.join(getattr(settings, 'MEDIA_ROOT', ''), source) if getattr(settings, 'MEDIA_ROOT', None) else None
        try_local = os.path.exists(local_path) if local_path else False

        # 1b) Альтернатива: отдельная папка импорта IMPORT_LOCAL_DIR (например, BASE_DIR/import_temp)
        if not try_local:
            import_root = getattr(settings, 'IMPORT_LOCAL_DIR', None)
            if import_root:
                alt_local_path = os.path.join(import_root, source.replace('import_temp'+os.sep, '').replace('import_temp/', ''))
                if os.path.exists(alt_local_path):
                    local_path = alt_local_path
                    try_local = True

        file_bytes = None
        filename = os.path.basename(source)

        if try_local:
            # Читаем локальный файл и сохраняем в хранилище под upload_to
            with open(local_path, 'rb') as f:
                file_bytes = f.read()
        else:
            # 2) Если это URL — скачиваем
            parsed = urlparse(source)
            if parsed.scheme in ('http', 'https'):
                try:
                    with urlopen(source) as resp:
                        file_bytes = resp.read()
                    # Попробуем взять имя файла из URL
                    filename = os.path.basename(parsed.path) or filename or 'image.jpg'
                except Exception:
                    file_bytes = None

        if file_bytes:
            # Сохраняем в ImageField — это спровоцирует запись в S3/локальное хранилище с учетом upload_to
            # Используем in-memory bytes
            file_obj = io.BytesIO(file_bytes)
            instance.image.save(filename, File(file_obj), save=True)
            # Если источник был локальным файлом и он находится в import_temp — можно удалить после загрузки
            if try_local:
                try:
                    os.remove(local_path)
                except Exception:
                    pass