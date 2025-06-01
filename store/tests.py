from django.test import TestCase
from django.urls import reverse # Для проверки URL-адресов моделей
from .models import Category, Product
from django.contrib.auth import get_user_model # Если будем тестировать что-то связанное с User
from django.test import Client
from .forms import OrderCreateForm
from django.conf import settings

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
        print("Тест test_category_creation для Category пройден.")

    def test_category_get_absolute_url(self):
        """Тест метода get_absolute_url для Category."""
        # Ожидаемый URL: /category/testovaya-kategoriya/
        expected_url = reverse('store:product_list_by_category', args=[self.category.slug])
        self.assertEqual(self.category.get_absolute_url(), expected_url)
        print("Тест test_category_get_absolute_url для Category пройден.")


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
        print("Тест test_product_creation для Product пройден.")

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



class OrderCreateFormTests(TestCase):
    def test_order_create_form_valid_data(self):
        """Тест: форма OrderCreateForm валидна с корректными данными."""
        form_data = {
            'first_name': 'Jan',
            'last_name': 'Kowalski',
            'email': 'jan.kowalski@example.com',
            'address_line_1': 'ul. Słoneczna 10',
            'address_line_2': 'apt. 5', # Опциональное поле
            'postal_code': '01-234',
            'city': 'Warszawa',
            'country': 'Polska'
        }
        form = OrderCreateForm(data=form_data)
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors.as_json()}")
        print("Тест test_order_create_form_valid_data пройден.")

    def test_order_create_form_missing_required_field(self):
        """Тест: форма OrderCreateForm невалидна, если отсутствует обязательное поле (например, first_name)."""
        form_data = {
            # 'first_name': 'Jan', # Пропускаем first_name
            'last_name': 'Kowalski',
            'email': 'jan.kowalski@example.com',
            'address_line_1': 'ul. Słoneczna 10',
            'postal_code': '01-234',
            'city': 'Warszawa',
            'country': 'Polska'
        }
        form = OrderCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('first_name', form.errors) # Проверяем, что ошибка именно в поле first_name
        print("Тест test_order_create_form_missing_required_field пройден.")

    def test_order_create_form_invalid_email(self):
        """Тест: форма OrderCreateForm невалидна с некорректным email."""
        form_data = {
            'first_name': 'Anna',
            'last_name': 'Nowak',
            'email': 'anna.nowak.example.com', # Некорректный email
            'address_line_1': 'ul. Kwiatowa 1',
            'postal_code': '12-345',
            'city': 'Kraków',
            'country': 'Polska'
        }
        form = OrderCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        print("Тест test_order_create_form_invalid_email пройден.")

    # Добавьте другие тесты для проверки различных сценариев валидации:
    # - Слишком длинные значения для полей CharField
    # - Некорректный формат почтового индекса (если есть специфические требования)
    # - и т.д.

    def test_order_create_form_address_line_2_optional(self):
        """Тест: форма OrderCreateForm валидна, даже если address_line_2 (опциональное поле) не заполнено."""
        form_data = {
            'first_name': 'Piotr',
            'last_name': 'Zieliński',
            'email': 'piotr.zielinski@example.com',
            'address_line_1': 'al. Niepodległości 100',
            # address_line_2 отсутствует
            'postal_code': '02-500',
            'city': 'Warszawa',
            'country': 'Polska'
        }
        form = OrderCreateForm(data=form_data)
        self.assertTrue(form.is_valid(), msg=f"Form errors: {form.errors.as_json()}")
        print("Тест test_order_create_form_address_line_2_optional пройден.")



class CartViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Test Kategoria", slug="test-kategoria")
        self.product1 = Product.objects.create(
            name="Test Produkt 1",
            slug="test-produkt-1",
            category=self.category,
            price="10.00",
            stock=5,
            available=True
        )
        self.product2 = Product.objects.create(
            name="Test Produkt 2",
            slug="test-produkt-2",
            category=self.category,
            price="25.50",
            stock=10,
            available=True
        )
        self.add_to_cart_url_p1 = reverse('store:cart_add', args=[self.product1.id])
        self.add_to_cart_url_p2 = reverse('store:cart_add', args=[self.product2.id])

    def test_cart_add_product_ajax(self):
        """Тест: добавление товара в корзину через AJAX POST."""
        # Добавляем первый товар
        response = self.client.post(
            self.add_to_cart_url_p1,
            {'quantity': 2, 'update': 'false'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest' # Важно для AJAX представлений
        )
        self.assertEqual(response.status_code, 200)
        json_response = response.json()
        self.assertEqual(json_response['status'], 'ok')
        self.assertEqual(json_response['cart_total_items'], 2)
        self.assertEqual(json_response['product_name'], self.product1.name)
        self.assertFalse(json_response['item_removed'])
        self.assertFalse(json_response['quantity_adjusted']) # Запрошенное количество не превышает остаток
        self.assertEqual(json_response['adjusted_quantity'], 2)

        # Проверяем сессию
        cart_session = self.client.session.get(settings.CART_SESSION_ID)
        self.assertIsNotNone(cart_session)
        self.assertIn(str(self.product1.id), cart_session)
        self.assertEqual(cart_session[str(self.product1.id)]['quantity'], 2)
        self.assertEqual(cart_session[str(self.product1.id)]['price'], str(self.product1.price))
        print("Тест test_cart_add_product_ajax (добавление) пройден.")

    def test_cart_add_product_update_quantity_ajax(self):
        """Тест: обновление количества товара в корзине через AJAX POST."""
        # Сначала добавляем товар
        self.client.post(
            self.add_to_cart_url_p1,
            {'quantity': 1}, # 'update' по умолчанию false
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Обновляем количество этого же товара
        response = self.client.post(
            self.add_to_cart_url_p1,
            {'quantity': 3, 'update': 'true'}, # Обновляем до 3
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        json_response = response.json()
        self.assertEqual(json_response['status'], 'ok')
        self.assertEqual(json_response['cart_total_items'], 3)
        self.assertEqual(json_response['adjusted_quantity'], 3)

        cart_session = self.client.session.get(settings.CART_SESSION_ID)
        self.assertEqual(cart_session[str(self.product1.id)]['quantity'], 3)
        print("Тест test_cart_add_product_update_quantity_ajax пройден.")

    def test_cart_add_product_exceed_stock_ajax(self):
        """Тест: добавление товара в корзину сверх остатка."""
        # product1 имеет stock=5
        response = self.client.post(
            self.add_to_cart_url_p1,
            {'quantity': 10, 'update': 'false'}, # Запрашиваем 10, доступно 5
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        json_response = response.json()
        self.assertEqual(json_response['status'], 'ok')
        self.assertEqual(json_response['cart_total_items'], 5) # Общее кол-во должно быть равно остатку
        self.assertTrue(json_response['quantity_adjusted']) # Количество было скорректировано
        self.assertEqual(json_response['adjusted_quantity'], 5) # Скорректированное кол-во равно остатку

        cart_session = self.client.session.get(settings.CART_SESSION_ID)
        self.assertEqual(cart_session[str(self.product1.id)]['quantity'], 5)
        print("Тест test_cart_add_product_exceed_stock_ajax пройден.")

    def test_cart_add_product_zero_quantity_removes_item_ajax(self):
        """Тест: установка количества товара в 0 должна удалить его из корзины."""
        # Сначала добавляем товар
        self.client.post(
            self.add_to_cart_url_p1,
            {'quantity': 2},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Обновляем количество до 0
        response = self.client.post(
            self.add_to_cart_url_p1,
            {'quantity': 0, 'update': 'true'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        json_response = response.json()
        self.assertEqual(json_response['status'], 'ok')
        self.assertEqual(json_response['cart_total_items'], 0)
        self.assertTrue(json_response['item_removed'])

        cart_session = self.client.session.get(settings.CART_SESSION_ID)
        self.assertNotIn(str(self.product1.id), cart_session)
        print("Тест test_cart_add_product_zero_quantity_removes_item_ajax пройден.")

    # Добавьте тесты для cart_remove
    def test_cart_remove_product_ajax(self):
        """Тест: удаление товара из корзины через AJAX POST."""
        # Добавляем два товара
        self.client.post(self.add_to_cart_url_p1, {'quantity': 1}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.client.post(self.add_to_cart_url_p2, {'quantity': 2}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        cart_session_before_remove = self.client.session.get(settings.CART_SESSION_ID)
        self.assertEqual(sum(item['quantity'] for item in cart_session_before_remove.values()), 3)

        remove_url_p1 = reverse('store:cart_remove', args=[self.product1.id])
        response = self.client.post(remove_url_p1, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        json_response = response.json()
        self.assertEqual(json_response['status'], 'ok')
        self.assertEqual(json_response['cart_total_items'], 2) # Остался только product2 с количеством 2

        cart_session_after_remove = self.client.session.get(settings.CART_SESSION_ID)
        self.assertNotIn(str(self.product1.id), cart_session_after_remove)
        self.assertIn(str(self.product2.id), cart_session_after_remove)
        self.assertEqual(cart_session_after_remove[str(self.product2.id)]['quantity'], 2)
        print("Тест test_cart_remove_product_ajax пройден.")