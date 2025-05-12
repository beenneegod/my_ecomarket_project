# test_stripe.py
import os
import stripe
import dotenv
from decimal import Decimal

def main_test_logic(): # Обернем основную логику в функцию
    print("Loading .env file...")
    dotenv.load_dotenv()

    print("Setting Stripe API key...")
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

    if not stripe.api_key:
        print("!!! Ошибка: Не найден STRIPE_SECRET_KEY в .env файле.")
        exit()

    print("Attempting to create Stripe Checkout session...")

# Минимальные данные для создания сессии
    session_data = {
            'mode': 'payment',
            'success_url': 'https://example.com/success?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': 'https://example.com/cancel',
            'line_items': [
                {
                    'price_data': {
                        'unit_amount': int(Decimal('15.99') * 100),
                        'currency': 'pln',
                        'product_data': {
                            'name': 'Minimal Test Product ASCII',
                            'metadata': {'product_db_id': 'test1'}
                        },
                    },
                    'quantity': 1,
                }
            ],
        }
    try:
        session = stripe.checkout.Session.create(**session_data)
        print("\n--- УСПЕХ! ---")
        print(f"Session ID: {session.id}")
        print(f"Session URL: {session.url}")

    except stripe.error.StripeError as e:
        print("\n--- ОШИБКА Stripe API ---")
        print(f"Stripe Error Type: {type(e)}")
        print(f"Error Message: {e}")
        # Попробуем вывести детали, если это ошибка API
        if hasattr(e, 'http_body') and e.http_body:
            print(f"HTTP Body: {e.http_body}")
        if hasattr(e, 'json_body') and e.json_body:
            print(f"JSON Body: {e.json_body}")

    except Exception as e:
        print("\n--- ОБЩАЯ ОШИБКА Python ---")
        print(f"Error Type: {type(e)}")
        print(f"Error Message: {e}")
        import traceback
        print("\nTraceback:")
        traceback.print_exc() # Печатаем полный трейсбек

# Этот блок гарантирует, что main_test_logic() вызовется только при прямом запуске файла
if __name__ == "__main__":
    main_test_logic()

