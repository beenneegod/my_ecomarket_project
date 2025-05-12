from django.test import TestCase
from django.urls import reverse # Для проверки URL-адресов моделей
from .models import Category, Product
from django.contrib.auth import get_user_model # Если будем тестировать что-то связанное с User
from django.test import Client

User = get_user_model() # Получаем активную модель пользователя

class CategoryModelTests(TestCase):

    def setUp(self):
        """Метод setUp вызывается перед каждым тестовым методом."""
        self.category = Category.objects.create(name="Тестовая Категория", slug="testovaya-kategoriya")

    def test_category_creation(self):
        """Тест создания объекта Category."""
        self.assertEqual(self.category.name, "Тестовая Категория")
        self.assertEqual(self.category.slug, "testovaya-kategoriya")
        self.assertEqual(str(self.category), "Тестовая Категория")
        print(f"Тест test_category_creation для Category пройден.")

    def test_category_get_absolute_url(self):
        """Тест метода get_absolute_url для Category."""
        # Ожидаемый URL: /category/testovaya-kategoriya/
        expected_url = reverse('store:product_list_by_category', args=[self.category.slug])
        self.assertEqual(self.category.get_absolute_url(), expected_url)
        print(f"Тест test_category_get_absolute_url для Category пройден.")


class ProductModelTests(TestCase):

    def setUp(self):
        """Настраиваем данные для тестов Product."""
        self.category = Category.objects.create(name="Электроника", slug="elektronika")
        self.product = Product.objects.create(
            name="Тестовый Товар",
            slug="testovyy-tovar", # Добавили слаг
            category=self.category,
            description="Описание тестового товара",
            price="199.99", # Цена как строка, DecimalField это обработает
            stock=10,
            available=True
        )

    def test_product_creation(self):
        """Тест создания объекта Product."""
        self.assertEqual(self.product.name, "Тестовый Товар")
        self.assertEqual(self.product.slug, "testovyy-tovar")
        self.assertEqual(self.product.category.name, "Электроника")
        self.assertEqual(float(self.product.price), 199.99) # Сравниваем как float
        self.assertEqual(self.product.stock, 10)
        self.assertTrue(self.product.available)
        self.assertEqual(str(self.product), "Тестовый Товар")
        print(f"Тест test_product_creation для Product пройден.")

class ProductListViewTests(TestCase):

    def setUp(self):
        # Создаем клиента для отправки запросов
        self.client = Client()
        # Создаем категорию
        self.category1 = Category.objects.create(name="Категория 1", slug="kategoriya-1")
        # Создаем несколько товаров
        self.product1 = Product.objects.create(name="Товар 1", category=self.category1, price="10.00", stock=5, available=True, slug="tovar-1")
        self.product2 = Product.objects.create(name="Товар 2", category=self.category1, price="20.00", stock=3, available=True, slug="tovar-2")
        self.product_unavailable = Product.objects.create(name="Недоступный Товар", category=self.category1, price="30.00", stock=0, available=False, slug="nedostupnyy-tovar")

    def test_product_list_view_status_code(self):
        """Тест: страница списка товаров возвращает статус 200 OK."""
        response = self.client.get(reverse('store:product_list')) # Используем имя URL
        self.assertEqual(response.status_code, 200)
        print("Тест test_product_list_view_status_code пройден.")

    def test_product_list_view_uses_correct_template(self):
        """Тест: страница списка товаров использует правильный шаблон."""
        response = self.client.get(reverse('store:product_list'))
        self.assertTemplateUsed(response, 'store/product_list.html')
        self.assertTemplateUsed(response, 'base.html') # Проверяем и базовый шаблон
        print("Тест test_product_list_view_uses_correct_template пройден.")

    def test_product_list_displays_available_products(self):
        """Тест: на странице отображаются только доступные товары."""
        response = self.client.get(reverse('store:product_list'))
        self.assertContains(response, self.product1.name) # Проверяем наличие имени товара 1
        self.assertContains(response, self.product2.name)
        self.assertNotContains(response, self.product_unavailable.name) # Проверяем отсутствие недоступного товара
        print("Тест test_product_list_displays_available_products пройден.")

    def test_product_list_by_category_view(self):
        """Тест: страница списка товаров по категории работает корректно."""
        # Создаем еще одну категорию и товар в ней для чистоты теста
        category2 = Category.objects.create(name="Категория 2", slug="kategoriya-2")
        product_in_cat2 = Product.objects.create(name="Товар в Категории 2", category=category2, price="50.00", slug="tovar-v-kategorii-2", available=True)

        # Запрос товаров из первой категории
        response_cat1 = self.client.get(reverse('store:product_list_by_category', args=[self.category1.slug]))
        self.assertEqual(response_cat1.status_code, 200)
        self.assertContains(response_cat1, self.product1.name)
        self.assertNotContains(response_cat1, product_in_cat2.name) # Убедимся, что товара из другой категории нет
        self.assertEqual(response_cat1.context['current_category'], self.category1)

        # Запрос товаров из второй категории
        response_cat2 = self.client.get(reverse('store:product_list_by_category', args=[category2.slug]))
        self.assertEqual(response_cat2.status_code, 200)
        self.assertContains(response_cat2, product_in_cat2.name)
        self.assertNotContains(response_cat2, self.product1.name)
        self.assertEqual(response_cat2.context['current_category'], category2)
        print("Тест test_product_list_by_category_view пройден.")