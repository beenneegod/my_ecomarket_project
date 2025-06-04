# config/settings.py

import os
from pathlib import Path
import dotenv # Импортируем dotenv
import logging

logger = logging.getLogger(__name__)
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Загрузка переменных окружения из .env файла ---
dotenv_path = BASE_DIR / '.env'
if dotenv_path.exists():
    dotenv.load_dotenv(dotenv_path=dotenv_path)
else:
    print("Warning: .env file not found. Ensure environment variables are set.")
# -----------------------------------------------------
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

if not DEBUG:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'


if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000 # 1 год в секундах
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True # Если используешь HTTPS, установи True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY and DEBUG: # В режиме DEBUG можно сгенерировать временный ключ
    # ... (логика генерации временного ключа или предупреждение)
    print("Warning: SECRET_KEY not set in .env for DEBUG mode. Using a temporary key or raise error in production.")
elif not SECRET_KEY and not DEBUG:
    raise ValueError("No SECRET_KEY set for Django application in production")


# --- Получаем ALLOWED_HOSTS из переменной окружения ---
allowed_hosts_str = os.getenv('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',') if host.strip()]
if DEBUG and not ALLOWED_HOSTS: # Если DEBUG и список пуст, добавляем стандартные
    ALLOWED_HOSTS.extend(['localhost', '127.0.0.1'])
elif not ALLOWED_HOSTS and not DEBUG: # Если не DEBUG и список пуст - это ошибка
    raise ValueError("ALLOWED_HOSTS must be set in production via environment variable.")
# ----------------------------------------------------

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'import_export',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'background_task',
    'axes',
    'rest_framework',
    'rest_framework.authtoken',
    # Наши приложения:
    'store.apps.StoreConfig', # Регистрируем приложение store
    'payments.apps.PaymentsConfig',
    'blog.apps.BlogConfig', # Add the blog app
    'carbon_calculator.apps.CarbonCalculatorConfig',
    'challenges.apps.ChallengesConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'axes.middleware.AxesMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls' # Указываем на файл urls.py в папке config

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Указываем Django искать шаблоны в папке 'templates' внутри КАЖДОГО приложения
        # А также в общей папке 'templates' в корне проекта (создадим ее позже)
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True, # Разрешаем искать шаблоны в папках приложений (store/templates/)
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'store.context_processors.cart',
                # Контекст процессор для корзины (добавим позже)
                # 'store.context_processors.cart',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/stable/ref/settings/#databases
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': os.getenv('DATABASE_NAME'),
        'USER': os.getenv('DATABASE_USER'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD'),
        'HOST': os.getenv('DATABASE_HOST'),
        'PORT': os.getenv('DATABASE_PORT', 5432),
    }
}
# Проверка наличия всех переменных БД
if DATABASES['default']['ENGINE'] == 'django.db.backends.mysql':
    # Убедимся, что порт не передается как пустая строка, если MySQL этого не любит
    if not DATABASES['default']['PORT']:
        del DATABASES['default']['PORT'] # Удаляем ключ PORT, если он пустой для MySQL
    # Дополнительные опции для MySQL можно добавить здесь, если они специфичны
    DATABASES['default'].setdefault('OPTIONS', {}).update({'charset': 'utf8mb4'})


# Password validation
# https://docs.djangoproject.com/en/stable/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# Internationalization
# https://docs.djangoproject.com/en/stable/topics/i18n/

LANGUAGE_CODE = 'pl'

TIME_ZONE = 'Europe/Warsaw'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images in our code)
# https://docs.djangoproject.com/en/stable/howto/static-files/

STATIC_URL = '/static/'
# Папка, куда `collectstatic` будет собирать все статические файлы для production
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Дополнительные папки, где Django будет искать статические файлы (кроме папок static внутри приложений)
STATICFILES_DIRS = [ BASE_DIR / 'static', ]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files (User uploaded files like product images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

if not DEBUG: # Настройки для ПРОДАКШЕНА (используем S3)
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')
    AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL') # Оставь пустым, если используешь Amazon S3
    AWS_S3_CUSTOM_DOMAIN = os.getenv('AWS_S3_CUSTOM_DOMAIN')

    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400', # Кеширование на 1 день
    }
    AWS_LOCATION = 'media' # Файлы будут в s3://<bucket_name>/media/
    AWS_DEFAULT_ACL = None # Сделать файлы публично читаемыми

    # Формирование MEDIA_URL
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
    elif AWS_S3_ENDPOINT_URL:
        # Для S3-совместимых хранилищ. Эта логика может потребовать адаптации
        # в зависимости от того, как твой провайдер формирует URL (path-style vs virtual-hosted style)
        # Часто django-storages сам формирует правильный URL для файла.
        # MEDIA_URL может быть просто корневым путем на этом эндпоинте для бакета.
        # Безопасный вариант - позволить django-storages генерировать полные URL для каждого файла,
        # а MEDIA_URL использовать для {{ MEDIA_URL }} в шаблонах, если нужно.
        # Пример для virtual-hosted style (если бакет доступен как bucket.endpoint.com):
        # endpoint_hostname = AWS_S3_ENDPOINT_URL.split('//')[-1]
        # MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.{endpoint_hostname}/{AWS_LOCATION}/'
        # Более простой вариант, если django-storages сам строит полный URL:
        MEDIA_URL = f'/{AWS_LOCATION}/' # Django будет использовать это как относительный путь для {{ MEDIA_URL }}
                                     # а file.url будет полным S3 URL.
                                     # Однако, если ты всегда используешь file.url, то точное значение MEDIA_URL в settings
                                     # для S3 (без кастомного домена) менее критично, если оно не пустое.
                                     # Твой существующий вариант:
                                     # base_s3_url = AWS_S3_ENDPOINT_URL
                                     # location_path = f"{AWS_LOCATION.strip('/')}/" if AWS_LOCATION else ""
                                     # MEDIA_URL = f'{base_s3_url}/{AWS_STORAGE_BUCKET_NAME}/{location_path}'
                                     # Этот вариант предполагает path-style доступ.
                                     # Оставим его, если он у тебя работал для S3-совместимого хранилища.
        base_s3_url = AWS_S3_ENDPOINT_URL.rstrip('/')
        location_inner = AWS_LOCATION.strip('/')
        bucket_name_part = AWS_STORAGE_BUCKET_NAME.strip('/')
        MEDIA_URL = f'{base_s3_url}/{bucket_name_part}/{location_inner}/'

    else: # Стандартный Amazon S3
        MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_LOCATION}/'

    # Убедимся, что MEDIA_URL всегда заканчивается на /
    if not MEDIA_URL.endswith('/'):
        MEDIA_URL += '/'

    # Проверка наличия ключевых переменных (можно сделать строже)
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME]):
        logger.warning("Ключевые настройки S3 для продакшена (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME) не полностью сконфигурированы. Проверьте переменные .env.")
    if not AWS_S3_REGION_NAME and not AWS_S3_ENDPOINT_URL and not AWS_S3_CUSTOM_DOMAIN: # Регион важен для AWS S3
        logger.warning("AWS_S3_REGION_NAME не установлена для стандартного AWS S3.")

else: # Настройки для РАЗРАБОТКИ (локальное хранение)
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'


# Default primary key field type
# https://docs.djangoproject.com/en/stable/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CART_SESSION_ID = 'cart'

# --- Stripe Keys ---
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
if not STRIPE_PUBLIC_KEY or not STRIPE_SECRET_KEY:
    print("Warning: Stripe keys not found in environment variables (.env).")   
if not STRIPE_WEBHOOK_SECRET:
    print("Warning: Stripe Webhook Secret not found in environment variables (.env). Webhook verification will fail.")
# -------------------
LOGIN_REDIRECT_URL = '/' # URL для перенаправления ПОСЛЕ успешного входа
LOGOUT_REDIRECT_URL = '/' # URL для перенаправления ПОСЛЕ выхода
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')
# Порт должен быть числом, конвертируем его
API_POST_AUTHOR_USERNAME = os.getenv('API_POST_AUTHOR_USERNAME', 'default_api_user')
try:
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587)) # 587 - частый порт по умолчанию для TLS
except (ValueError, TypeError):
    EMAIL_PORT = 587
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD') # Пароль или API ключ

# Конвертируем строковые 'True'/'False' из .env в булевы значения
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() == 'true'

# Email отправителя по умолчанию
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER) # Часто совпадает с логином

# Опционально: Управление соединениями (может помочь при некоторых проблемах)
EMAIL_TIMEOUT = 60 # Время ожидания ответа от сервера (секунды)

# Проверка наличия основных настроек для SMTP
if not all([EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]):
    print("Warning: SMTP Email settings (EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD) are not fully configured in .env. Real email sending might fail.")

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = 0.25
AXES_LOCKOUT_TEMPLATE = 'registration/lockout.html'
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_VERBOSE = True 
AXES_ENABLE_ADMIN = True


AVERAGE_ANNUAL_CO2_FOOTPRINT_PL_KG = 5600