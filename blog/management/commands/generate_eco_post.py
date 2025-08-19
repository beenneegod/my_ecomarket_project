# blog/management/commands/generate_eco_post.py

import os
import random
import re
import json # Upewnij się, że json jest zaimportowany
import traceback
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.db import transaction
from blog.models import Post
import google.generativeai as genai
import logging
from .eco_topics_pl import POLISH_ECO_TOPICS

logger = logging.getLogger(__name__)
User = get_user_model()

# --- Configuration Constants ---
# Nazwa zmiennej środowiskowej dla klucza Gemini API
ENV_GEMINI_API_KEY = "GEMINI_API_KEY_FOR_BLOG"

# Nazwa użytkownika Django do przypisywania postów generowanych przez AI
AI_AUTHOR_USERNAME = 'api_content_bot' # Upewnij się, że ten użytkownik istnieje w bazie danych

# Nazwy modeli Gemini
PRIMARY_GEMINI_MODEL = 'gemini-1.5-flash-latest' # Główny model do użycia
FALLBACK_GEMINI_MODEL = 'gemini-pro'


def load_prompt_template(topic_prompt_str: str, topic_slug_for_hashtag_str: str) -> str | None:
    # Ścieżka do pliku szablonu podpowiedzi względem katalogu tej komendy
    command_dir = os.path.dirname(__file__)
    file_path = os.path.join(command_dir, 'gemini_blog_prompt.txt')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        # Uwaga: NIE używaj .format() na całym szablonie, bo zawiera on klamry JSON.
        # Wykonujemy celowe podstawienia tylko naszych placeholderów.
        formatted = (
            prompt_template
            .replace('{topic_prompt}', topic_prompt_str)
            .replace('{topic_slug_for_hashtag}', topic_slug_for_hashtag_str)
        )

        # Opcjonalnie ostrzeż, jeśli placeholdery nie zostały znalezione
        if '{topic_prompt}' not in prompt_template or '{topic_slug_for_hashtag}' not in prompt_template:
            logger.warning('Szablon podpowiedzi nie zawiera jednego z oczekiwanych placeholderów: {topic_prompt} lub {topic_slug_for_hashtag}.')

        return formatted
    except FileNotFoundError:
        logger.error(f"Nie znaleziono pliku szablonu podpowiedzi: {file_path}")
        return None
    except Exception as e:
        logger.error(f"Nie udało się załadować lub sformatować szablonu podpowiedzi: {e}")
        return None

# --- Funkcja generowania treści za pomocą Gemini ---
def generate_content_with_gemini(topic_prompt_text: str, gemini_api_key: str) -> dict | None:
    logger.info(f"Kontaktowanie się z API Gemini w celu wygenerowania posta na temat: '{topic_prompt_text}'...")

    if not gemini_api_key: # Sprawdzenie pustego klucza (z get_gemini_api_key)
        logger.error("Brak klucza Gemini API. Generowanie anulowane.")
        return None

    try:
        genai.configure(api_key=gemini_api_key)
        logger.debug("Klucz Gemini API został pomyślnie skonfigurowany dla tego wywołania.")
    except Exception as e:
        logger.exception(f"Nie udało się skonfigurować Gemini API z podanym kluczem: {e}")
        return None

    model = None
    try:
        logger.debug(f"Próba inicjalizacji głównego modelu Gemini ('{PRIMARY_GEMINI_MODEL}')...")
        model = genai.GenerativeModel(PRIMARY_GEMINI_MODEL)
    except Exception as e_primary:
        logger.warning(f"Nie udało się zainicjalizować głównego modelu Gemini ('{PRIMARY_GEMINI_MODEL}'): {e_primary}")
        try:
            logger.info(f"Próba użycia modelu zapasowego ('{FALLBACK_GEMINI_MODEL}')...")
            model = genai.GenerativeModel(FALLBACK_GEMINI_MODEL)
        except Exception as e_fallback:
            logger.exception(f"Nie udało się zainicjalizować zapasowego modelu Gemini ('{FALLBACK_GEMINI_MODEL}'): {e_fallback}")
            return None

    if not model:
        logger.error("Model Gemini nie może zostać zainicjalizowany.")
        return None

    topic_slug = slugify(topic_prompt_text, allow_unicode=True).replace("-", "_") if topic_prompt_text else "ecotips"

    formatted_prompt = load_prompt_template(topic_prompt_text, topic_slug)
    if not formatted_prompt:
        return None # Błąd już zalogowany w load_prompt_template

    logger.info(f"Wysyłanie sformatowanej podpowiedzi do API Gemini (długość: {len(formatted_prompt)} znaków)...")

    try:
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,
            response_mime_type="application/json" # ŻĄDAMY JSON
        ) # type: ignore

        # Ustawiamy safety_settings, aby uniknąć blokad bezpieczeństwa
        # dla niewinnych tematów, jeśli takie się zdarzają. Dostosuj w razie potrzeby.
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
            logger.info("Otrzymano surową odpowiedź od Gemini (przez response.text). Próba bezpośredniego parsowania JSON.")
        elif response.candidates and response.candidates[0].content.parts:
            generated_json_text = response.candidates[0].content.parts[0].text
            logger.info("Surowa odpowiedź wyodrębniona z kandydatów Gemini.")
        else:
            error_message = "API Gemini zwróciło odpowiedź bez treści tekstowej lub prawidłowych kandydatów."
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback: # type: ignore
                feedback = response.prompt_feedback # type: ignore
                error_message += f" Powód blokady podpowiedzi: {feedback.block_reason}."
                if feedback.block_reason_message:
                     error_message += f" Wiadomość: {feedback.block_reason_message}."
            logger.error(error_message)
            return None

        if not generated_json_text:
            logger.error("Nie udało się wyodrębnić tekstu z odpowiedzi Gemini do parsowania JSON.")
            return None

        try:
            # Usuwamy możliwe owinięcia ```json ... ``` przed parsowaniem
            # To może być zbędne, jeśli response_mime_type="application/json" działa idealnie
            match_md_json = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", generated_json_text, re.DOTALL)
            if match_md_json:
                json_to_parse = match_md_json.group(1).strip()
                logger.info("JSON wyodrębniony z bloku Markdown ```json ... ```.")
            else:
                json_to_parse = generated_json_text.strip()

            generated_data = json.loads(json_to_parse)
            title = generated_data.get("title")
            body = generated_data.get("body")

            if isinstance(title, str) and title.strip() and \
               isinstance(body, str) and body.strip():
                logger.info("Gemini pomyślnie wygenerował i sparsował treść JSON.")
                return {"title": title.strip(), "body": body.strip()}
            else:
                missing_fields_msg = []
                if not (isinstance(title, str) and title.strip()): missing_fields_msg.append("'title'")
                if not (isinstance(body, str) and body.strip()): missing_fields_msg.append("'body'")
                logger.error(f"Sparsowany JSON z Gemini nie zawiera wymaganych pól, pola są puste lub mają nieprawidłowy typ: {', '.join(missing_fields_msg)}. Otrzymane dane: {generated_data}")
                return None
        except json.JSONDecodeError as e_json:
            logger.error(f"Błąd dekodowania JSON: {e_json}. Tekst do parsowania (pierwsze 500 znaków): '{generated_json_text[:500]}'")
            # Jeśli response_mime_type="application/json" nie zadziałał i nie zwrócił JSON,
            # można tutaj zostawić starą logikę z re.search dla całego tekstu, jeśli to konieczne.
            # Ale lepiej jest sprawić, by API zwracało czysty JSON.
            return None

    except Exception as e_api:
        logger.exception(f"BŁĄD KRYTYCZNY podczas żądania do API Gemini lub przetwarzania odpowiedzi: {e_api}")
        # traceback.print_exc() jest już zawarty w logger.exception
        return None

class Command(BaseCommand):
    help = 'Generuje i publikuje nowy post na blogu o tematyce ekologicznej przy użyciu API Gemini.'
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(f"--- {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}: Rozpoczęcie generowania eko-postu ---"))

        gemini_key = self.get_gemini_api_key() # Twoja metoda get_gemini_api_key już używa self.stdout
        if not gemini_key:
        # Komunikat o błędzie jest już wyświetlany w get_gemini_api_key
            return

        try:
            author = User.objects.get(username=AI_AUTHOR_USERNAME)
            self.stdout.write(self.style.SUCCESS(f"Autor '{author.username}' dla postów znaleziony."))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"BŁĄD KRYTYCZNY: Użytkownik-autor '{AI_AUTHOR_USERNAME}' nie został znaleziony w bazie danych. Proszę utworzyć tego użytkownika."
            ))
            return

        # Używamy tematów z zewnętrznego pliku
        chosen_topic_prompt = random.choice(POLISH_ECO_TOPICS)
        self.stdout.write(f"Wybrany temat do generowania postu: '{chosen_topic_prompt}'")

        ai_content_data = generate_content_with_gemini(chosen_topic_prompt, gemini_key)

        if not ai_content_data:
            self.stdout.write(self.style.ERROR(
                "Nie udało się wygenerować prawidłowej treści (tytuł/treść) przy użyciu API Gemini. Zobacz szczegóły w logach powyżej."
            ))
            return

        title = ai_content_data["title"]
        body = ai_content_data["body"]
        
        self.stdout.write(f"Wygenerowany tytuł: '{title}'")
        body_preview = body[:150].replace("\n", " ").replace("\r", " ")
        self.stdout.write(f"Wygenerowana treść (początek): '{body_preview}...'")

        slug_base = slugify(title, allow_unicode=True)
        if not slug_base: 
            self.stdout.write(self.style.WARNING(f"Nie można utworzyć sluga z tytułu '{title}'. Używanie podpowiedzi tematu jako podstawy sluga."))
            slug_base = slugify(chosen_topic_prompt[:60], allow_unicode=True)
            if not slug_base: 
                self.stdout.write(self.style.WARNING("Nie można utworzyć sluga z tematu. Używanie sluga opartego na znaczniku czasu."))
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
            self.stdout.write(self.style.WARNING("Nie można określić max_length dla pola slug. Pomijanie sprawdzania długości dla podstawy sluga."))

        while Post.objects.filter(slug=unique_slug).exists():
            unique_slug = f"{slug_base}-{counter}"
            if slug_max_length and len(unique_slug) > slug_max_length:
                self.stdout.write(self.style.ERROR(f"Wygenerowany unikalny slug '{unique_slug}' przekracza maksymalną długość {slug_max_length}. Tworzenie postu może się nie powieść."))
                break 
            counter += 1
        
        self.stdout.write(f"Wygenerowany unikalny slug: '{unique_slug}'")
        
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
                    f"Pomyślnie utworzono i opublikowano nowy post! ID: {new_post.id}, Tytuł: '{new_post.title}'"
                ))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Błąd podczas tworzenia postu w bazie danych: {e}"))
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
        
        self.stdout.write(self.style.SUCCESS(f"--- {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}: Generowanie eko-postu zakończone ---"))


    def get_gemini_api_key(self) -> str | None:
        gemini_api_key = os.getenv(ENV_GEMINI_API_KEY)
        if not gemini_api_key:
            self.stdout.write(self.style.ERROR(
                f"BŁĄD KRYTYCZNY: Klucz API Gemini nie został znaleziony w zmiennej środowiskowej '{ENV_GEMINI_API_KEY}'. "
                "Proszę ustawić tę zmienną w pliku .env."
            ))
            return None

        known_placeholders = [
            "AIzaSyYOUR_API_KEY_HERE_REPLACE_ME",  
        ]
        if gemini_api_key in known_placeholders:
            self.stdout.write(self.style.ERROR(
                f"BŁĄD KRYTYCZNY: Klucz API ze zmiennej środowiskowej '{ENV_GEMINI_API_KEY}' "
                "jest placeholderem lub wcześniej zakodowanym na stałe kluczem. Proszę ustawić NOWY, prawidłowy klucz API."
            ))
            return None

        self.stdout.write(self.style.SUCCESS(
            f"Klucz API Gemini pomyślnie pobrany ze zmiennej środowiskowej '{ENV_GEMINI_API_KEY}'."
        ))
        return gemini_api_key