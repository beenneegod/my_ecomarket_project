# payments/tests.py
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock # Для мокирования Stripe API
from store.models import Product, Category # Для создания тестовых продуктов в корзине
from store.cart import Cart # Для работы с корзиной
from django.conf import settings

class PaymentCheckoutTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Gadgets", slug="gadgets")
        self.product = Product.objects.create(
            name="Test Gadget", slug="test-gadget", category=self.category, price="100.00", stock=10
        )
        self.checkout_url = reverse('payments:checkout')

        # Добавим товар в корзину для теста
        cart = Cart(self.client.session) # Получаем корзину через self.client.session
        cart.add(product=self.product, quantity=1)
        self.client.session.save() # Важно сохранить сессию после изменений

    @patch('stripe.checkout.Session.create') # Мокируем метод Stripe API
    def test_checkout_and_payment_post_success(self, mock_stripe_session_create):
        # Настраиваем, что будет возвращать мок-объект Stripe
        mock_session = MagicMock()
        mock_session.id = 'cs_test_123'
        mock_session.url = 'https://stripe.com/test_payment_url'
        mock_stripe_session_create.return_value = mock_session

        # Данные формы для POST-запроса
        form_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com',
            'address_line_1': '123 Main St',
            'postal_code': '00-000',
            'city': 'Test City',
            'country': 'Polska'
        }

        response = self.client.post(self.checkout_url, form_data)

        # Проверяем, что был вызван метод Stripe API
        mock_stripe_session_create.assert_called_once()
        called_args, called_kwargs = mock_stripe_session_create.call_args
        
        # Проверяем некоторые параметры, переданные в Stripe
        self.assertEqual(called_kwargs['mode'], 'payment')
        self.assertIn('line_items', called_kwargs)
        self.assertEqual(len(called_kwargs['line_items']), 1)
        self.assertEqual(called_kwargs['line_items'][0]['price_data']['product_data']['name'], self.product.name)
        self.assertEqual(called_kwargs['metadata']['email'], 'test@example.com') # Проверяем, что email передан (в примере кода Stripe это customer_email)
                                                                                # или metadata, если вы так настроили

        # Проверяем, что произошло перенаправление на URL Stripe
        self.assertEqual(response.status_code, 303) # 303 See Other - стандарт для редиректа после POST
        self.assertEqual(response.url, mock_session.url)

        print("Тест test_checkout_and_payment_post_success пройден.")