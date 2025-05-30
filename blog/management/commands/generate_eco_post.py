# blog/management/commands/generate_eco_post.py

import os
import random
import re
import json # Убедись, что json импортирован
import traceback
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.db import transaction
from blog.models import Post
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

# --- Configuration Constants ---
# Имя переменной окружения для ключа Gemini API (оставим, но не будем главным)
ENV_GEMINI_API_KEY = "GEMINI_API_KEY_FOR_BLOG"

# Django username for attributing AI-generated posts
AI_AUTHOR_USERNAME = 'api_content_bot' # Ensure this user exists in your database

# Gemini Model Names
PRIMARY_GEMINI_MODEL = 'gemini-1.5-flash-latest' # Primary model to use
FALLBACK_GEMINI_MODEL = 'gemini-pro'


def load_prompt_template(topic_prompt_str: str, topic_slug_for_hashtag_str: str) -> str | None:
    # Путь к файлу шаблона промпта относительно директории этой команды
    command_dir = os.path.dirname(__file__)
    file_path = os.path.join(command_dir, 'gemini_blog_prompt.txt')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        return prompt_template.format(
            topic_prompt=topic_prompt_str,
            topic_slug_for_hashtag=topic_slug_for_hashtag_str
        )
    except FileNotFoundError:
        logger.error(f"Файл шаблона промпта не найден по пути: {file_path}")
        return None
    except KeyError as e:
        logger.error(f"Ключ форматирования не найден в шаблоне промпта: {e}. Убедись, что {{topic_prompt}} и {{topic_slug_for_hashtag}} присутствуют.")
        return None
    except Exception as e:
        logger.error(f"Не удалось загрузить или отформатировать шаблон промпта: {e}")
        return None

# --- Function for Generating Content with Gemini ---
def generate_content_with_gemini(topic_prompt_text: str, gemini_api_key: str) -> dict | None:
    logger.info(f"Обращение к Gemini API для генерации поста на тему: '{topic_prompt_text}'...")

    if not gemini_api_key: # Проверка на пустой ключ (из get_gemini_api_key)
        logger.error("Ключ Gemini API отсутствует. Генерация отменена.")
        return None

    try:
        genai.configure(api_key=gemini_api_key)
        logger.debug("Ключ Gemini API успешно сконфигурирован для этого вызова.")
    except Exception as e:
        logger.exception(f"Не удалось сконфигурировать Gemini API с предоставленным ключом: {e}")
        return None

    model = None
    try:
        logger.debug(f"Попытка инициализации основной модели Gemini ('{PRIMARY_GEMINI_MODEL}')...")
        model = genai.GenerativeModel(PRIMARY_GEMINI_MODEL)
    except Exception as e_primary:
        logger.warning(f"Не удалось инициализировать основную модель Gemini ('{PRIMARY_GEMINI_MODEL}'): {e_primary}")
        try:
            logger.info(f"Попытка использовать запасную модель ('{FALLBACK_GEMINI_MODEL}')...")
            model = genai.GenerativeModel(FALLBACK_GEMINI_MODEL)
        except Exception as e_fallback:
            logger.exception(f"Не удалось инициализировать запасную модель Gemini ('{FALLBACK_GEMINI_MODEL}'): {e_fallback}")
            return None

    if not model:
        logger.error("Модель Gemini не может быть инициализирована.")
        return None

    topic_slug = slugify(topic_prompt_text, allow_unicode=True).replace("-", "_") if topic_prompt_text else "ecotips"

    formatted_prompt = load_prompt_template(topic_prompt_text, topic_slug)
    if not formatted_prompt:
        return None # Ошибка уже залогирована в load_prompt_template

    logger.info(f"Отправка отформатированного промпта в Gemini API (длина: {len(formatted_prompt)} символов)...")

    try:
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,
            response_mime_type="application/json" # ЗАПРАШИВАЕМ JSON
        ) # type: ignore

        # Устанавливаем safety_settings, чтобы попытаться избежать блокировок по безопасности
        # для невинных тем, если такое происходит. Настрой по необходимости.
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        response = model.generate_content(
            formatted_prompt, 
            generation_config=generation_config,
            safety_settings=safety_settings
        )

        generated_json_text = None
        if response.text:
            generated_json_text = response.text
            logger.info("Получен сырой ответ от Gemini (через response.text). Попытка прямого парсинга JSON.")
        elif response.candidates and response.candidates[0].content.parts:
            generated_json_text = response.candidates[0].content.parts[0].text
            logger.info("Сырой ответ извлечен из candidates Gemini.")
        else:
            error_message = "Gemini API вернул ответ без текстового содержимого или валидных candidates."
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback: # type: ignore
                feedback = response.prompt_feedback # type: ignore
                error_message += f" Причина блокировки промпта: {feedback.block_reason}."
                if feedback.block_reason_message:
                     error_message += f" Сообщение: {feedback.block_reason_message}."
            logger.error(error_message)
            return None

        if not generated_json_text:
            logger.error("Не удалось извлечь текст из ответа Gemini для парсинга JSON.")
            return None

        try:
            # Убираем возможные ```json ... ``` обертки перед парсингом
            # Это может быть излишним, если response_mime_type="application/json" работает идеально
            match_md_json = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", generated_json_text, re.DOTALL)
            if match_md_json:
                json_to_parse = match_md_json.group(1).strip()
                logger.info("JSON извлечен из Markdown блока ```json ... ```.")
            else:
                json_to_parse = generated_json_text.strip()

            generated_data = json.loads(json_to_parse)
            title = generated_data.get("title")
            body = generated_data.get("body")

            if isinstance(title, str) and title.strip() and \
               isinstance(body, str) and body.strip():
                logger.info("Gemini успешно сгенерировал и распарсил JSON контент.")
                return {"title": title.strip(), "body": body.strip()}
            else:
                missing_fields_msg = []
                if not (isinstance(title, str) and title.strip()): missing_fields_msg.append("'title'")
                if not (isinstance(body, str) and body.strip()): missing_fields_msg.append("'body'")
                logger.error(f"Распарсенный JSON из Gemini не содержит обязательных полей, поля пусты или имеют неверный тип: {', '.join(missing_fields_msg)}. Полученные данные: {generated_data}")
                return None
        except json.JSONDecodeError as e_json:
            logger.error(f"Ошибка декодирования JSON: {e_json}. Текст для парсинга (первые 500 симв.): '{generated_json_text[:500]}'")
            # Если response_mime_type="application/json" не сработал и вернулся не JSON,
            # можно здесь оставить старую логику с re.search для всего текста, если очень нужно.
            # Но лучше добиться, чтобы API возвращал чистый JSON.
            return None

    except Exception as e_api:
        logger.exception(f"КРИТИЧЕСКАЯ ОШИБКА во время запроса к Gemini API или обработки ответа: {e_api}")
        # traceback.print_exc() в logger.exception уже включен
        return None

class Command(BaseCommand):
    help = 'Generates and publishes a new eco-themed blog post using the Gemini API.'
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(f"--- {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}: Запуск генерации эко-поста ---"))

        gemini_key = self.get_gemini_api_key() # Твой метод get_gemini_api_key уже использует self.stdout
        if not gemini_key:
        # Сообщение об ошибке уже выводится в get_gemini_api_key
            return

        try:
            author = User.objects.get(username=AI_AUTHOR_USERNAME)
            self.stdout.write(self.style.SUCCESS(f"Автор '{author.username}' для постов найден."))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"КРИТИЧЕСКАЯ ОШИБКА: Пользователь-автор '{AI_AUTHOR_USERNAME}' не найден в базе. Пожалуйста, создайте этого пользователя."
            ))
            return

        topics = [
            "The benefits of seasonal vegetables for your table from EcoMarket",
            "Simple and tasty green smoothie recipe with products from EcoMarket",
            "How to choose the best organic fruits and vegetables: a guide from EcoMarket",
            "DIY natural cleaning products: eco-friendly home cleaning with EcoMarket",
            "Zero Waste in the kitchen: tips for reducing waste from EcoMarket",
            "Why it's important to choose natural cosmetics: a review from EcoMarket",
            "Eco-bottles and reusable tableware: your contribution to fighting plastic with EcoMarket",
            "Vertical gardening and microgreens at home: tips from EcoMarket",
            "Composting food waste: a simple guide for beginners from EcoMarket",
            "Energy saving in everyday life: easy steps towards an eco-friendly home with EcoMarket"
        ]
        chosen_topic_prompt = random.choice(topics)
        self.stdout.write(f"Chosen topic for post generation: '{chosen_topic_prompt}'")

        ai_content_data = generate_content_with_gemini(chosen_topic_prompt, gemini_key)

        if not ai_content_data:
            self.stdout.write(self.style.ERROR(
                "Failed to generate valid content (title/body) using the Gemini API. See logs above for details."
            ))
            return

        title = ai_content_data["title"]
        body = ai_content_data["body"]
        
        self.stdout.write(f"Generated title: '{title}'")
        body_preview = body[:150].replace("\n", " ").replace("\r", " ")
        self.stdout.write(f"Generated body (start): '{body_preview}...'")

        slug_base = slugify(title, allow_unicode=True)
        if not slug_base: 
            self.stdout.write(self.style.WARNING(f"Could not create slug from title '{title}'. Using topic prompt for slug base."))
            slug_base = slugify(chosen_topic_prompt[:60], allow_unicode=True)
            if not slug_base: 
                self.stdout.write(self.style.WARNING("Could not create slug from topic. Using timestamp-based slug."))
                slug_base = f"eco-post-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        
        unique_slug = slug_base
        counter = 1
        
        try:
            slug_max_length = Post._meta.get_field('slug').max_length
            effective_max_base_length = slug_max_length - 5 
            if len(slug_base) > effective_max_base_length:
                slug_base = slug_base[:effective_max_base_length]
                unique_slug = slug_base
        except Exception: 
            slug_max_length = None
            self.stdout.write(self.style.WARNING("Could not determine max_length for slug field. Skipping length check for slug base."))

        while Post.objects.filter(slug=unique_slug).exists():
            unique_slug = f"{slug_base}-{counter}"
            if slug_max_length and len(unique_slug) > slug_max_length:
                self.stdout.write(self.style.ERROR(f"Generated unique slug '{unique_slug}' exceeds max length of {slug_max_length}. Post creation may fail."))
                break 
            counter += 1
        
        self.stdout.write(f"Generated unique slug: '{unique_slug}'")
        
        try:
            with transaction.atomic():
                new_post = Post.objects.create(
                    title=title,
                    slug=unique_slug,
                    author=author,
                    body=body,
                    published_at=timezone.now(), 
                    status='published'
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Successfully created and published new post! ID: {new_post.id}, Title: '{new_post.title}'"
                ))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creating post in the database: {e}"))
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
        
        self.stdout.write(self.style.SUCCESS(f"--- {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}: Eco-post generation finished ---"))


    def get_gemini_api_key(self) -> str | None:
        gemini_api_key = os.getenv(ENV_GEMINI_API_KEY)
        if not gemini_api_key:
            self.stdout.write(self.style.ERROR(
                f"КРИТИЧЕСКАЯ ОШИБКА: Ключ Gemini API не найден в переменной окружения '{ENV_GEMINI_API_KEY}'. "
                "Пожалуйста, установите эту переменную в вашем .env файле."
            ))
            return None

        known_placeholders = [
            "AIzaSyYOUR_API_KEY_HERE_REPLACE_ME",  
        ]
        if gemini_api_key in known_placeholders:
            self.stdout.write(self.style.ERROR(
                f"КРИТИЧЕСКАЯ ОШИБКА: Ключ API из переменной окружения '{ENV_GEMINI_API_KEY}' "
                "является плейсхолдером или ранее жестко закодированным ключом. Пожалуйста, установите НОВЫЙ, валидный ключ API."
            ))
            return None

        self.stdout.write(self.style.SUCCESS(
            f"Ключ Gemini API успешно получен из переменной окружения '{ENV_GEMINI_API_KEY}'."
        ))
        return gemini_api_key