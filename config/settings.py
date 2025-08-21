# config/settings.py

import os
from pathlib import Path
import dotenv
from datetime import timedelta
import logging  # <-- добавляем импорт

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
    SECURE_HSTS_SECONDS = 31536000 # 1 год в секундах
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True # Если используешь HTTPS, установи True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Доверяем заголовкам прокси (Railway/Heroku и т.п.), чтобы избежать бесконечных редиректов HTTPS
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-insecure-secret-key'  # DO NOT USE IN PRODUCTION
        logger.warning("SECRET_KEY not set in .env; using an insecure development key.")
    else:
        raise ValueError("No SECRET_KEY set for Django application in production")


# --- Получаем ALLOWED_HOSTS из переменной окружения ---
allowed_hosts_str = os.getenv('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',') if host.strip()]
if DEBUG and not ALLOWED_HOSTS: # Если DEBUG и список пуст, добавляем стандартные
    ALLOWED_HOSTS.extend(['localhost', '127.0.0.1'])
elif not ALLOWED_HOSTS and not DEBUG: # Если не DEBUG и список пуст - это ошибка
    raise ValueError("ALLOWED_HOSTS must be set in production via environment variable.")
if 'healthcheck.railway.app' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('healthcheck.railway.app')
# ----------------------------------------------------

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.sitemaps',
    'import_export',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storages',  # required for S3Boto3Storage in production
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
    'places.apps.PlacesConfig',
    'chat.apps.ChatConfig',
    'channels',
    'csp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'csp.middleware.CSPMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
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
ASGI_APPLICATION = 'config.asgi.application'


# Database
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DATABASE_URL = os.getenv('DATABASE_URL')

def _is_valid_db_url(url: str) -> bool:
    if not url:
        return False
    if url.startswith('${'):  # неразрешённый плейсхолдер Railway
        return False
    return '://' in url

if _is_valid_db_url(DATABASE_URL):
    try:
        import dj_database_url
        DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
        logger.info("DATABASES: using DATABASE_URL")
    except Exception as e:
        logger.warning("Invalid DATABASE_URL (%s). Falling back to individual DB_* vars.", e)
        DATABASES = {
            'default': {
                'ENGINE': DB_ENGINE,
                'NAME': os.getenv('DATABASE_NAME'),
                'USER': os.getenv('DATABASE_USER'),
                'PASSWORD': os.getenv('DATABASE_PASSWORD'),
                'HOST': os.getenv('DATABASE_HOST'),
                'PORT': os.getenv('DATABASE_PORT', 5432),
                'CONN_MAX_AGE': 600,
            }
        }
elif DEBUG and not os.getenv('DATABASE_NAME'):
    DATABASES = { 'default': { 'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3' } }
    logger.info("DATABASES: using SQLite (DEBUG)")
else:
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': os.getenv('DATABASE_NAME'),
            'USER': os.getenv('DATABASE_USER'),
            'PASSWORD': os.getenv('DATABASE_PASSWORD'),
            'HOST': os.getenv('DATABASE_HOST'),
            'PORT': os.getenv('DATABASE_PORT', 5432),
            'CONN_MAX_AGE': 600,
        }
    }
    logger.info("DATABASES: using individual DB_* vars")

# Настройки MySQL (на всякий случай)
if DATABASES['default']['ENGINE'] == 'django.db.backends.mysql':
    if not DATABASES['default']['PORT']:
        del DATABASES['default']['PORT']
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

# Wymuś polski jako jedyny język w interfejsie
LANGUAGES = [
    ('pl', 'Polski'),
]
LOCALE_PATHS = [ BASE_DIR / 'locale' ]

USE_TZ = True


# Static files (CSS, JavaScript, Images in our code)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [ BASE_DIR / 'static', ]

# Определяем storage один раз, без дублей
if DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# Media files (User uploaded files like product images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

if not DEBUG: # Настройки для ПРОДАКШЕНА (используем S3)
    # Используем S3 для хранения медиа-файлов в продакшене
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
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
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False      # public, unsigned URLs
    AWS_S3_FILE_OVERWRITE = False

    # Формирование MEDIA_URL
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
    elif AWS_S3_ENDPOINT_URL:
        base = AWS_S3_ENDPOINT_URL.rstrip('/')
        bucket = AWS_STORAGE_BUCKET_NAME.strip('/')
        loc = AWS_LOCATION.strip('/')
        MEDIA_URL = f'{base}/{bucket}/{loc}/'
    else:
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

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
# Default primary key field type
# https://docs.djangoproject.com/en/stable/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CART_SESSION_ID = 'cart'

# Channels: use Redis in production when REDIS_URL is provided, else in-memory for dev
REDIS_URL = os.getenv('REDIS_URL')
if REDIS_URL:
    config = {'hosts': [REDIS_URL]}
    if REDIS_URL.startswith('rediss://'):
        config = {'hosts': [{'address': REDIS_URL, 'ssl': True}]}
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': config,
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
}
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
if EMAIL_USE_SSL and EMAIL_USE_TLS:
    logger.warning("Both EMAIL_USE_SSL and EMAIL_USE_TLS were True. Forcing TLS only.")
    EMAIL_USE_SSL = False
# Email отправителя по умолчанию
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER) # Часто совпадает с логином

# Опционально: Управление соединениями (может помочь при некоторых проблемах)
EMAIL_TIMEOUT = 60 # Время ожидания ответа от сервера (секунды)

# Проверка наличия основных настроек для SMTP
if not all([EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]):
    print("Warning: SMTP Email settings (EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD) are not fully configured in .env. Real email sending might fail.")
    # In development, fall back to console backend so emails show up in the runserver/process_tasks output
    if DEBUG:
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_FAILURE_LIMIT = 10
# Use timedelta for clarity; 0.25 hours = 15 minutes
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_TEMPLATE = 'registration/lockout.html'
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_VERBOSE = True 
AXES_ENABLE_ADMIN = True
AXES_BEHIND_REVERSE_PROXY = True
AXES_REVERSE_PROXY_HEADER = 'HTTP_X_FORWARDED_FOR'

AVERAGE_ANNUAL_CO2_FOOTPRINT_PL_KG = 5600


# --- Дополнительно: логирование в файлы logs/info.log и logs/error.log ---
LOGS_DIR = BASE_DIR / 'logs'
os.makedirs(LOGS_DIR, exist_ok=True)

# Папка для локальных импортов изображений (помимо MEDIA_ROOT). Можно переопределить через .env IMPORT_LOCAL_DIR
IMPORT_LOCAL_DIR = os.getenv('IMPORT_LOCAL_DIR', str(BASE_DIR / 'import_temp'))
try:
    os.makedirs(IMPORT_LOCAL_DIR, exist_ok=True)
except Exception as e:
    logger.warning("Could not create IMPORT_LOCAL_DIR (%s): %s", IMPORT_LOCAL_DIR, e)

# CSRF_TRUSTED_ORIGINS из окружения (через запятую)
csrf_trusted = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if csrf_trusted:
    CSRF_TRUSTED_ORIGINS = []
    for o in csrf_trusted.split(','):
        o = o.strip()
        if not o:
            continue
        if o.startswith('http://') or o.startswith('https://'):
            CSRF_TRUSTED_ORIGINS.append(o)
        else:
            CSRF_TRUSTED_ORIGINS.append(f'https://{o}')
            if DEBUG:
                CSRF_TRUSTED_ORIGINS.append(f'http://{o}')

# Базовый URL сайта для генерации абсолютных ссылок в письмах
# Например: https://myecomarket.pl (без завершающего слэша)
SITE_URL = os.getenv('SITE_URL', 'http://localhost:8000').rstrip('/')
IN_RAILWAY = bool(os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_STATIC_URL'))
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': { 'verbose': { 'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s' }, },
    'handlers': {
        'console': { 'class': 'logging.StreamHandler', 'formatter': 'verbose', },
        'file_info': { 'level': 'INFO', 'class': 'logging.FileHandler', 'filename': str(LOGS_DIR / 'info.log'), 'formatter': 'verbose', 'encoding': 'utf-8', },
        'file_error': { 'level': 'ERROR', 'class': 'logging.FileHandler', 'filename': str(LOGS_DIR / 'error.log'), 'formatter': 'verbose', 'encoding': 'utf-8', },
    },
    'root': {
        'handlers': ['console'] if (IN_RAILWAY and not DEBUG) else ['console', 'file_info', 'file_error'],
        'level': 'INFO',
    },
}

# --- Content Security Policy (CSP) ---
# Разрешаем наши статики/медиа, а также используемые CDN: Bootstrap, AOS, Bootstrap Icons, SweetAlert2, Google Fonts
# В DEV допускаем 'unsafe-inline' для стилей/скриптов из шаблонов, в PROD желательно перейти на nonce/sha.
CSP_DEFAULT_SRC = ("'self'",)
# Скрипты: наши + используемые CDN; в DEBUG добавляем 'unsafe-inline' для инлайновых фрагментов.
CSP_SCRIPT_SRC = (
    "'self'",
    'https://cdn.jsdelivr.net',
    'https://unpkg.com',
    'https://cdn.jsdelivr.net/npm/sweetalert2@11',
)

# Стили: наши + CDN; в DEBUG допускаем инлайн-стили.
CSP_STYLE_SRC = (
    "'self'",
    'https://cdn.jsdelivr.net',
    'https://fonts.googleapis.com',
    'https://unpkg.com',
)

CSP_FONT_SRC = (
    "'self'",
    'https://fonts.gstatic.com',
    'https://cdn.jsdelivr.net',
    'data:',
)

# Изображения: свои, data/blob, и (по необходимости) внешние домены.
CSP_IMG_SRC = (
    "'self'",
    'data:',
    'blob:',
    'https://*.tile.openstreetmap.org',
    'https://unpkg.com',
)
AWS_IMG_SOURCES = []
try:
    if not DEBUG:
        if 'AWS_S3_CUSTOM_DOMAIN' in globals() and AWS_S3_CUSTOM_DOMAIN:
            AWS_IMG_SOURCES.append(f'https://{AWS_S3_CUSTOM_DOMAIN}')
        if 'AWS_S3_ENDPOINT_URL' in globals() and AWS_S3_ENDPOINT_URL:
            AWS_IMG_SOURCES.append(AWS_S3_ENDPOINT_URL)
except Exception:
    pass
if AWS_IMG_SOURCES:
    CSP_IMG_SRC = CSP_IMG_SRC + tuple(AWS_IMG_SOURCES)

# Also include MEDIA_URL host and common S3 bucket hosts in CSP for images
try:
    from urllib.parse import urlparse
    _media = globals().get('MEDIA_URL')
    if _media:
        _pu = urlparse(_media)
        if _pu.scheme in ('http', 'https') and _pu.netloc:
            CSP_IMG_SRC = CSP_IMG_SRC + (f"{_pu.scheme}://{_pu.netloc}",)
    _bucket = globals().get('AWS_STORAGE_BUCKET_NAME')
    _region = globals().get('AWS_S3_REGION_NAME')
    if _bucket:
        # Regionless legacy endpoint and regioned endpoint
        CSP_IMG_SRC = CSP_IMG_SRC + (f"https://{_bucket}.s3.amazonaws.com",)
        if _region:
            CSP_IMG_SRC = CSP_IMG_SRC + (f"https://{_bucket}.s3.{_region}.amazonaws.com",)
except Exception:
    pass

# Разрешаем WebSocket-соединения к своему хосту
CSP_CONNECT_SRC = (
    "'self'",
    'ws:',
    'wss:',
)
CSP_OBJECT_SRC = ("'none'",)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_BASE_URI = ("'self'",)

# No inline scripts required now; all JS is external. Keep nonces off.
if 'CSP_NONCE_IN_CONTEXT' in globals():
    del globals()['CSP_NONCE_IN_CONTEXT']