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
AI_AUTHOR_USERNAME = 'Ecomarket'  # Убедись, что такой пользователь существует в базе

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

    if not gemini_api_key:  # Sprawdzenie pustego klucza (z get_gemini_api_key)
        logger.error("Brak klucza Gemini API. Generowanie anulowane.")
        return None

    try:
        genai.configure(api_key=gemini_api_key)
        logger.debug("Klucz Gemini API został pomyślnie skonfigurowany dla tego wywołania.")
    except Exception as e:
        logger.exception(f"Nie udało się skonfigurować Gemini API z podanym kluczem: {e}")
        return None

    # Przygotowanie promptu bazowego
    topic_slug = slugify(topic_prompt_text, allow_unicode=True).replace("-", "_") if topic_prompt_text else "ecotips"
    base_prompt = load_prompt_template(topic_prompt_text, topic_slug)
    if not base_prompt:
        return None  # Błąd już zalogowany w load_prompt_template

    def strict_suffix(lang: str = 'pl') -> str:
        if lang == 'pl':
            return ("\n\nWAŻNE: ZWRÓĆ WYŁĄCZNIE surowy JSON bez żadnych bloków kodu, bez komentarza, bez dodatkowego tekstu."
                    " Nie używaj znaczników ```json. Tylko poprawny JSON z polami 'title' i 'body'.")
        return ("\n\nIMPORTANT: Return ONLY raw JSON. No prose, no markdown, no code fences."
                " Provide valid JSON object with 'title' and 'body' keys only.")

    attempts = [
        {"model": PRIMARY_GEMINI_MODEL, "temperature": 0.7, "suffix": ""},
        {"model": PRIMARY_GEMINI_MODEL, "temperature": 0.4, "suffix": strict_suffix('pl')},
        {"model": FALLBACK_GEMINI_MODEL, "temperature": 0.2, "suffix": strict_suffix('pl')},
    ]

    def try_parse_json(text: str) -> dict | None:
        if not text:
            return None
        s = text.strip()
        # 1) Usuń fenced code blocks ```json ... ```
        m = re.search(r"```json\s*(\{[\s\S]*\})\s*```", s, re.DOTALL)
        if m:
            s = m.group(1).strip()
        # 2) Spróbuj bezpośrednio
        try:
            return json.loads(s)
        except Exception:
            pass
        # 3) Spróbuj znaleźć największy zbalansowany blok JSON od pierwszej '{'
        start = s.find('{')
        end = s.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = s[start:end + 1]
            # Upewnij się, że nawiasy są zbalansowane
            depth = 0
            for ch in candidate:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth < 0:
                        break
            if depth == 0:
                try:
                    return json.loads(candidate)
                except Exception:
                    pass
        return None

    # Bezpieczne ustawienia
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    last_error_preview = None
    for idx, cfg in enumerate(attempts, start=1):
        model_name = cfg["model"]
        temp = cfg["temperature"]
        prompt = base_prompt + cfg["suffix"]
        logger.info(f"Próba {idx}/%d z modelem '%s' i temperaturą %.2f..." % (len(attempts), model_name, temp))

        # Inicjalizuj model dla tej próby
        try:
            model = genai.GenerativeModel(model_name)
        except Exception as e_model:
            logger.warning(f"Nie udało się zainicjalizować modelu '{model_name}' w próbie {idx}: {e_model}")
            continue

        try:
            generation_config = genai.types.GenerationConfig(
                temperature=temp,
                response_mime_type="application/json",
            )  # type: ignore

            response = model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings,
            )

            raw_text = None
            if getattr(response, 'text', None):
                raw_text = response.text
            elif getattr(response, 'candidates', None):
                try:
                    raw_text = response.candidates[0].content.parts[0].text
                except Exception:
                    raw_text = None

            if not raw_text:
                msg = "Pusta odpowiedź tekstowa od Gemini."
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:  # type: ignore
                    fb = response.prompt_feedback  # type: ignore
                    msg += f" Powód: {getattr(fb, 'block_reason', '?')}"
                logger.warning(f"Próba {idx}: {msg}")
                continue

            data = try_parse_json(raw_text)
            if not data:
                last_error_preview = raw_text[:500]
                logger.warning(f"Próba {idx}: nie udało się sparsować JSON. Podgląd: '{last_error_preview}'")
                continue

            title = data.get("title")
            body = data.get("body")
            if isinstance(title, str) and title.strip() and isinstance(body, str) and body.strip():
                logger.info(f"Próba {idx}: sukces — poprawny JSON.")
                return {"title": title.strip(), "body": body.strip()}
            else:
                logger.warning(f"Próba {idx}: JSON bez wymaganych pól lub puste wartości. Dane: {data}")
                continue

        except Exception as e_api:
            # Specjalna obsługa ograniczenia klucza przez HTTP referrer (403)
            err_txt = str(e_api)
            if "API_KEY_HTTP_REFERRER_BLOCKED" in err_txt or ("referer" in err_txt.lower() and "blocked" in err_txt.lower()):
                logger.error(
                    "Wykryto błąd 403: API_KEY_HTTP_REFERRER_BLOCKED — Klucz Gemini ma ograniczenia HTTP referrer. "
                    "Wywołania backendu (serwer-serwer) nie wysyłają referera, więc taki klucz jest odrzucany. "
                    "Rozwiązanie: utwórz NOWY klucz API przeznaczony dla backendu (bez ograniczeń HTTP referrer) "
                    "lub usuń restrykcje referera z obecnego klucza. Następnie ustaw go w zmiennej środowiskowej '%s'." % ENV_GEMINI_API_KEY
                )
                # Nie ma sensu ponawiać — zakończ pętlę prób
                return None

            # Inne wyjątki: loguj i próbuj dalej
            preview = ''
            try:
                preview = (raw_text or '')[:200]  # type: ignore
            except Exception:
                preview = ''
            logger.warning(f"Próba {idx}: wyjątek podczas generowania/parsing: {e_api}. Podgląd: '{preview}'")
            continue

    if last_error_preview:
        logger.error(f"Wszystkie próby nieudane. Ostatni podgląd odpowiedzi: '{last_error_preview}'")
    else:
        logger.error("Wszystkie próby nieudane bez treści do podglądu.")
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