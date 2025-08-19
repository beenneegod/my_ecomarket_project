"""
Polski tekst do komunikatów używanych w komendach zarządzania.
"""

# Komunikaty błędów
ERROR_API_KEY_NOT_FOUND = "BŁĄD KRYTYCZNY: Klucz API Gemini nie został znaleziony w zmiennej środowiskowej '{0}'. Proszę ustawić tę zmienną w pliku .env."
ERROR_API_KEY_PLACEHOLDER = "BŁĄD KRYTYCZNY: Klucz API ze zmiennej środowiskowej '{0}' jest placeholderem lub wcześniej zakodowanym na stałe kluczem. Proszę ustawić NOWY, prawidłowy klucz API."
ERROR_AUTHOR_NOT_FOUND = "BŁĄD KRYTYCZNY: Użytkownik-autor '{0}' nie został znaleziony w bazie danych. Proszę utworzyć tego użytkownika."
ERROR_CONTENT_GENERATION = "Nie udało się wygenerować prawidłowej treści (tytuł/treść) przy użyciu API Gemini. Zobacz szczegóły w logach powyżej."
ERROR_DB_POST_CREATION = "Błąd podczas tworzenia postu w bazie danych: {0}"
ERROR_SLUG_TOO_LONG = "Wygenerowany unikalny slug '{0}' przekracza maksymalną długość {1}. Tworzenie postu może się nie powieść."

# Komunikaty powodzenia
SUCCESS_AUTHOR_FOUND = "Autor '{0}' dla postów znaleziony."
SUCCESS_API_KEY_FOUND = "Klucz API Gemini pomyślnie pobrany ze zmiennej środowiskowej '{0}'."
SUCCESS_POST_CREATED = "Pomyślnie utworzono i opublikowano nowy post! ID: {0}, Tytuł: '{1}'"
SUCCESS_ECO_POST_START = "--- {0}: Rozpoczęcie generowania eko-postu ---"
SUCCESS_ECO_POST_END = "--- {0}: Generowanie eko-postu zakończone ---"

# Komunikaty informacyjne
INFO_CHOSEN_TOPIC = "Wybrany temat do generowania postu: '{0}'"
INFO_GENERATED_TITLE = "Wygenerowany tytuł: '{0}'"
INFO_GENERATED_BODY = "Wygenerowana treść (początek): '{0}...'"
INFO_GENERATED_SLUG = "Wygenerowany unikalny slug: '{0}'"
INFO_SLUG_FROM_TOPIC = "Nie można utworzyć sluga z tytułu '{0}'. Używanie podpowiedzi tematu jako podstawy sluga."
INFO_SLUG_FROM_TIMESTAMP = "Nie można utworzyć sluga z tematu. Używanie sluga opartego na znaczniku czasu."
INFO_SLUG_MAX_LENGTH = "Nie można określić max_length dla pola slug. Pomijanie sprawdzania długości dla podstawy sluga."
