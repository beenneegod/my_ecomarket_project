# blog/management/commands/generate_eco_post.py

import os
import random
import re
import json
import traceback
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.db import transaction
from blog.models import Post # Ensure your Post model is correctly imported
import google.generativeai as genai

User = get_user_model()

# --- Configuration Constants ---
# Имя переменной окружения для ключа Gemini API (оставим, но не будем главным)
ENV_GEMINI_API_KEY = "GEMINI_API_KEY_FOR_BLOG"

DEFAULT_GEMINI_API_KEY = "AIzaSyCNqV54G4iLBGi2c431UhQvWXXJdhdTjyM"
# Django username for attributing AI-generated posts
AI_AUTHOR_USERNAME = 'beenneegod' # Ensure this user exists in your database

# Gemini Model Names
PRIMARY_GEMINI_MODEL = 'gemini-1.5-flash-latest' # Primary model to use
FALLBACK_GEMINI_MODEL = 'gemini-pro'

# --- Function for Generating Content with Gemini ---
def generate_content_with_gemini(topic_prompt: str, gemini_api_key: str) -> dict | None:
    print(f"INFO: Contacting Gemini API to generate a post on: '{topic_prompt}'...")

    if not gemini_api_key or gemini_api_key == "AIzaSyYOUR_API_KEY_HERE_REPLACE_ME": # Проверка на плейсхолдер
        print("ERROR: Gemini API key is missing or is a placeholder. Please set a valid API key in the script.")
        return None

    try:
        # Configure the API key specifically for this function call
        genai.configure(api_key=gemini_api_key)
        print("INFO: Gemini API key configured successfully for this call.")
    except Exception as e:
        print(f"ERROR: Failed to configure Gemini API with the provided key: {e}")
        traceback.print_exc()
        return None

    model = None
    try:
        print(f"INFO: Attempting to initialize primary Gemini model ('{PRIMARY_GEMINI_MODEL}')...")
        model = genai.GenerativeModel(PRIMARY_GEMINI_MODEL)
    except Exception as e_primary:
        print(f"WARNING: Failed to initialize primary Gemini model ('{PRIMARY_GEMINI_MODEL}'): {e_primary}")
        try:
            print(f"INFO: Attempting to use fallback model ('{FALLBACK_GEMINI_MODEL}')...")
            model = genai.GenerativeModel(FALLBACK_GEMINI_MODEL)
        except Exception as e_fallback:
            print(f"ERROR: Failed to initialize fallback Gemini model ('{FALLBACK_GEMINI_MODEL}'): {e_fallback}")
            traceback.print_exc()
            return None
    
    if not model:
        print("ERROR: Gemini model could not be initialized.")
        return None

    topic_slug_for_hashtag = slugify(topic_prompt, allow_unicode=True).replace("-", "_") if topic_prompt else "ecotips"

    prompt = f"""
    Proszę, wciel się w rolę content managera bloga sklepu internetowego "EcoMarket", który specjalizuje się w produktach organicznych i zdrowym stylu życia.
    Twoim zadaniem jest napisanie posta na bloga na następujący temat:
    "{topic_prompt}"

    Wymagania dotyczące artykułu:
    1.  **Tytuł:** Stwórz angażujący i przyciągający uwagę tytuł (od 5 do 15 słów).
    2.  **Tekst artykułu:** Napisz główną część artykułu, około 300-500 słów. Tekst powinien być:
        * Informacyjny i użyteczny dla czytelników.
        * Napisany przyjaznym i przystępnym językiem.
        * Ustrukturyzowany (np. używając krótkich akapitów, ewentualnie list, jeśli pasuje to do tematu).
        * Unikalny (unikaj bezpośredniego kopiowania).
        * Zawierać praktyczne porady lub informacje, które mogą zainteresować czytelników EcoMarket.
        * Jeśli to możliwe, dodaj kilka ciekawostek lub faktów związanych z tematem.
        * Jeśli temat dotyczy produktów, możesz wspomnieć o nich, ale nie rób tego w sposób nachalny.
        * Unikaj bezpośrednich reklam produktów EcoMarket, skup się na wartości merytorycznej.
        * Jeśli temat dotyczy zdrowego stylu życia, ekologii lub zrównoważonego rozwoju, postaraj się uwzględnić te aspekty.
        * Jeśli temat dotyczy sezonowych produktów, możesz wspomnieć o ich dostępności w EcoMarket.
        * Jeśli temat dotyczy przepisów kulinarnych, możesz podać przykładowy przepis lub składniki, które można znaleźć w EcoMarket.
        * W języku polskim, z użyciem polskich znaków diakrytycznych.
    5.  **Styl:** Przyjazny, profesjonalny, zrozumiały dla szerokiego grona odbiorców.
    11. **Formatowanie:** Użyj prostego formatowania tekstu, takiego jak:
        * Nagłówki (H2, H3) dla sekcji artykułu.
        * Listy punktowane lub numerowane, jeśli pasuje do treści.
        * Pogrubienia lub kursywy dla podkreślenia ważnych informacji.
        * Piękne akapity, aby tekst był czytelny i przyjemny dla oka.
    6.  **Długość:** Cały artykuł powinien mieć od 300 do 500 słów.
    7.  **Struktura:** Artykuł powinien być podzielony na logiczne sekcje, z nagłówkami, jeśli to możliwe.
    8.  **Hasła SEO:** Użyj naturalnie słów kluczowych związanych z tematem, ale nie przesadzaj z ich ilością.
    9.  **Cytaty i źródła:** Jeśli używasz danych lub statystyk, podaj źródła lub linki do nich.
    10. **Linki:** Jeśli to możliwe, dodaj linki do powiązanych artykułów na blogu EcoMarket lub do produktów, ale nie rób tego w sposób nachalny.
    3.  **Hashtagi:** Na końcu artykułu dodaj 3-4 odpowiednie hashtagi (np. #ecomarket #zdrowejedzenie #{topic_slug_for_hashtag}).
    4.  **Format odpowiedzi:** Całą odpowiedź przekaż ŚCIŚLE w formacie JSON o następującej strukturze:
        {{
          "title": "Twój wygenerowany tytuł",
          "body": "Twój wygenerowany pełny tekst artykułu, zawierający hashtagi na końcu."
        }}
    Proszę nie dodawać żadnych innych wyjaśnień ani tekstu przed lub po obiekcie JSON. Tylko sam JSON.
    """

    print(f"INFO: Sending prompt to Gemini API (prompt length: {len(prompt)} characters)...")
    
    try:
        generation_config = genai.types.GenerationConfig(temperature=0.7) # type: ignore
        response = model.generate_content(prompt, generation_config=generation_config)

        generated_text = None
        try:
            if response.text:
                generated_text = response.text
                print("INFO: Raw response received from Gemini (via response.text).")
        except AttributeError:
            print("INFO: response.text not available, trying via candidates.")
        except Exception as e_text_access:
            print(f"WARNING: Error accessing response.text: {e_text_access}. Trying via candidates.")

        if not generated_text:
            if response.candidates and response.candidates[0].content.parts:
                generated_text = response.candidates[0].content.parts[0].text
                print("INFO: Raw response received from Gemini (via candidates[0].content.parts[0].text).")
            else:
                error_message = "Gemini API returned a response without text content, valid candidates, or content parts."
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback: # type: ignore
                    feedback = response.prompt_feedback # type: ignore
                    error_message += f" Prompt feedback block reason: {feedback.block_reason}."
                    if feedback.block_reason_message:
                        error_message += f" Message: {feedback.block_reason_message}."
                print(f"ERROR: {error_message}")
                return None
        
        if not generated_text:
            print("ERROR: Failed to extract any text from the Gemini response.")
            return None

        json_str = ""
        match_markdown = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", generated_text, re.DOTALL)
        if match_markdown:
            json_str = match_markdown.group(1).strip()
            print("INFO: JSON extracted from markdown ```json ... ``` block.")
        elif generated_text.strip().startswith("{") and generated_text.strip().endswith("}"):
            json_str = generated_text.strip()
            print("INFO: Gemini response recognized as a clean JSON object.")
        else:
            match_curly = re.search(r"(\{((?:[^{}]*|\{(?1)\})*)\})", generated_text)
            if match_curly:
                json_str = match_curly.group(0).strip()
                print("WARNING: JSON extracted from text using a general regex. Validate correctness.")
            else:
                print(f"ERROR: Could not find a JSON-like structure in the Gemini response. Response snippet: {generated_text[:1000]}...")
                return None
        
        try:
            generated_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"ERROR: JSON decoding failed: {e}. Extracted string for JSON: '{json_str}'")
            print(f"Full Gemini response snippet: {generated_text[:1000]}...")
            return None

        title = generated_data.get("title")
        body = generated_data.get("body")

        if isinstance(title, str) and title.strip() and \
           isinstance(body, str) and body.strip():
            print("INFO: Gemini successfully generated and parsed content (title and body).")
            return {"title": title.strip(), "body": body.strip()}
        else:
            missing_fields = []
            if not isinstance(title, str) or not title.strip(): missing_fields.append("'title' (non-empty string)")
            if not isinstance(body, str) or not body.strip(): missing_fields.append("'body' (non-empty string)")
            print(f"ERROR: JSON from Gemini is missing required fields, fields are empty, or have incorrect types: {', '.join(missing_fields)}. Received: {generated_data}")
            return None

    except Exception as e_api:
        print(f"CRITICAL ERROR during Gemini API request or response processing: {e_api}")
        traceback.print_exc()
        return None

class Command(BaseCommand):
    help = 'Generates and publishes a new eco-themed blog post using the Gemini API.'

    def get_gemini_api_key(self) -> str | None:
        """
        Retrieves the Gemini API key.
        For temporary testing, it prioritizes the hardcoded DEFAULT_GEMINI_API_KEY.
        It will also check the environment variable as a fallback.
        """
        # 1. Пытаемся получить из переменной окружения (как более безопасный вариант)
        key_from_env = os.getenv(ENV_GEMINI_API_KEY)
        if key_from_env:
            self.stdout.write(self.style.SUCCESS(
                f"Gemini API key successfully retrieved from environment variable '{ENV_GEMINI_API_KEY}'."
            ))
            if key_from_env == "AIzaSyYOUR_API_KEY_HERE_REPLACE_ME": # Проверка на плейсхолдер из env
                 self.stdout.write(self.style.WARNING(
                    "The API key from environment variable appears to be a placeholder. "
                    "Falling back to DEFAULT_GEMINI_API_KEY from script."
                ))
            else:
                return key_from_env

        # 2. Если из окружения нет или это плейсхолдер, используем ключ из кода (для временной отладки)
        script_key = DEFAULT_GEMINI_API_KEY
        if not script_key or script_key == "AIzaSyYOUR_API_KEY_HERE_REPLACE_ME":
            self.stdout.write(self.style.ERROR(
                "CRITICAL ERROR: Gemini API key is not set or is a placeholder in the script. "
                f"Please set a valid API key in DEFAULT_GEMINI_API_KEY or the '{ENV_GEMINI_API_KEY}' environment variable."
            ))
            return None
        
        self.stdout.write(self.style.WARNING(
            f"Using DEFAULT_GEMINI_API_KEY directly from the script. "
            "Remember to switch to environment variables for production."
        ))
        return script_key

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"--- {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}: Starting eco-post generation ---"))

        gemini_key = self.get_gemini_api_key()
        if not gemini_key:
            self.stdout.write(self.style.ERROR("Operation aborted due to missing or invalid Gemini API key."))
            return

        try:
            author = User.objects.get(username=AI_AUTHOR_USERNAME)
            self.stdout.write(self.style.SUCCESS(f"Author '{author.username}' for posts found."))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"CRITICAL ERROR: Author user '{AI_AUTHOR_USERNAME}' not found in the database. Please create this user."
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