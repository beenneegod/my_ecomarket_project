# carbon_calculator/models.py
from django.db import models
from django.conf import settings
from store.models import Product  # Upewnij się, że model Product jest dostępny do importu
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from decimal import Decimal


class Region(models.Model):
    code = models.CharField(max_length=10, unique=True, verbose_name="Kod kraju/regionu")
    name = models.CharField(max_length=100, unique=True, verbose_name="Nazwa regionu/kraju")
    grid_intensity_kg_per_kwh = models.DecimalField(
        max_digits=8, decimal_places=4,
        verbose_name="Intensywność sieci (kg CO2/kWh)"
    )
    is_default = models.BooleanField(default=False, verbose_name="Domyślny region")

    class Meta:
        verbose_name = "Region"
        verbose_name_plural = "Regiony"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

class ActivityCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nazwa kategorii")
    slug = models.SlugField(max_length=110, unique=True, blank=True, verbose_name="Slug (do URL)")
    description = models.TextField(blank=True, null=True, verbose_name="Opis kategorii")
    icon_class = models.CharField(max_length=50, blank=True, null=True, verbose_name="Klasa ikony (np. Bootstrap Icons)")
    order = models.PositiveIntegerField(default=0, verbose_name="Kolejność wyświetlania")

    class Meta:
        verbose_name = "Kategoria aktywności"
        verbose_name_plural = "Kategorie aktywności"
        ordering = ['order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            if len(self.slug) > 110:
                self.slug = self.slug[:110]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class EmissionFactor(models.Model):
    FIELD_TYPES = [
        ('number', 'Pole liczbowe'),
        ('select', 'Lista rozwijana'),
        # ('radio', 'Przyciski radiowe'),
        # ('checkbox', 'Pole wyboru'),
    ]

    activity_category = models.ForeignKey(
        ActivityCategory,
        on_delete=models.PROTECT,
        related_name='factors',
        verbose_name="Kategoria aktywności"
    )
    name = models.CharField(max_length=255, verbose_name="Nazwa wewnętrzna czynnika/aktywności")
    description = models.TextField(blank=True, null=True, verbose_name="Szczegółowy opis czynnika (dla administratora)")
    
    unit_name = models.CharField(max_length=50, verbose_name="Jednostka miary do obliczeń CO2") # np. "km", "kg", "kWh"
    co2_kg_per_unit = models.DecimalField(
        max_digits=12, decimal_places=6,
        verbose_name="Emisja CO2 (kg) na jednostkę"
    )
    
    data_source_info = models.TextField(blank=True, null=True, verbose_name="Źródło danych dla współczynnika (raport, rok)")
    valid_from = models.DateField(null=True, blank=True, verbose_name="Obowiązuje od")
    valid_to = models.DateField(null=True, blank=True, verbose_name="Obowiązuje do")
    form_question_text = models.TextField(verbose_name="Treść pytania dla użytkownika w formularzu")
    form_field_type = models.CharField(
        max_length=20,
        choices=FIELD_TYPES,
        default='number',
        verbose_name="Typ pola w formularzu"
    )
    form_field_options = models.JSONField(
        null=True, blank=True,
        verbose_name="Opcje dla pola 'select' (JSON)",
        help_text='Dla "select": {"1": "Etykieta 1", "0.15": "Etykieta 2"}. Klucze muszą być LICZBAMI (np. "1", "0.15"), bo są używane bezpośrednio w obliczeniach jako mnożnik/wartość.'
    )
    form_placeholder = models.CharField(max_length=100, blank=True, null=True, verbose_name="Tekst podpowiedzi (placeholder) dla pola liczbowego")
    form_help_text = models.TextField(blank=True, null=True, verbose_name="Podpowiedź do pola w formularzu")
    
    periodicity_options_for_form = models.JSONField(
        null=True, blank=True,
        verbose_name="Opcje częstotliwości dla wprowadzania (JSON)",
        help_text='Przykład: {"per_week": {"label": "na tydzień", "annual_multiplier": 52}, "per_month": {"label": "na miesiąc", "annual_multiplier": 12}}. Jeśli puste, zakłada się wartość roczną lub określoną w unit_name.'
    )

    is_active = models.BooleanField(default=True, verbose_name="Aktywny (używać w kalkulatorze)")
    order = models.PositiveIntegerField(default=0, verbose_name="Kolejność pytania w kategorii")
    # Jeśli True, zamiast co2_kg_per_unit użyj intensywności sieci regionu (dla prądu)
    use_region_grid_intensity = models.BooleanField(
        default=False,
        verbose_name="Użyj intensywności sieci regionu (zamiast co2/kg na jednostkę)"
    )
    # Czy aktywność dotyczy gospodarstwa domowego — dzielić na liczbę osób
    per_household = models.BooleanField(
        default=False,
        verbose_name="Dotyczy gospodarstwa domowego (dzielić na liczbę osób)"
    )
    # Granice zdroworozsądkowe (opcjonalne)
    min_reasonable_value = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Minimalna rozsądna wartość"
    )
    max_reasonable_value = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Maksymalna rozsądna wartość"
    )

    class Meta:
        verbose_name = "Współczynnik emisji"
        verbose_name_plural = "Współczynniki emisji"
        ordering = ['activity_category__order', 'activity_category__name', 'order', 'name']

    def __str__(self):
        return f"{self.name} ({self.activity_category.name})"

    def clean(self):
        super().clean()
        # Walidacja form_field_options
        if self.form_field_type == 'select' and self.form_field_options:
            if not isinstance(self.form_field_options, dict):
                raise ValidationError({'form_field_options': 'form_field_options musi być słownikiem (dict).'})
            for k, v in self.form_field_options.items():
                if not isinstance(k, str):
                    raise ValidationError({'form_field_options': 'Klucze w form_field_options muszą być łańcuchami (str).'})
                if not (isinstance(v, (str, int, float))):
                    raise ValidationError({'form_field_options': 'Wartości w form_field_options muszą być tekstem lub liczbą.'})
                # Klucze muszą być liczbowe (parsowane do Decimal), bo są używane jako wartość do obliczeń
                try:
                    Decimal(str(k))
                except Exception:
                    raise ValidationError({'form_field_options': f"Klucz '{k}' nie jest liczbą. Użyj liczb (np. '1', '0.15')."})
        # Walidacja periodicity_options_for_form
        if self.periodicity_options_for_form:
            if not isinstance(self.periodicity_options_for_form, dict):
                raise ValidationError({'periodicity_options_for_form': 'periodicity_options_for_form musi być słownikiem (dict).'})
            for k, v in self.periodicity_options_for_form.items():
                if not isinstance(k, str):
                    raise ValidationError({'periodicity_options_for_form': 'Klucze w periodicity_options_for_form muszą być łańcuchami (str).'})
                if not isinstance(v, dict):
                    raise ValidationError({'periodicity_options_for_form': 'Wartości w periodicity_options_for_form muszą być słownikami.'})
                if 'label' not in v or 'annual_multiplier' not in v:
                    raise ValidationError({'periodicity_options_for_form': 'Każdy element musi zawierać label i annual_multiplier.'})

class UserFootprintSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Użytkownik"
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True, verbose_name="Klucz sesji (dla anonimowych)")
    inputs_data = models.JSONField(verbose_name="Dane wprowadzone przez użytkownika i ich kontekst")
    total_co2_emissions_kg_annual = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name="Całkowity roczny ślad węglowy (kg CO2-ekw.)"
    )
    category_breakdown_kg_annual = models.JSONField(
        verbose_name="Roczny podział na kategorie (kg CO2-ekw.)",
        null=True, blank=True
    )
    calculation_version = models.CharField(max_length=50, default="1.0", verbose_name="Wersja kalkulatora/metodologii")
    calculated_at = models.DateTimeField(auto_now_add=True, verbose_name="Data obliczenia")

    class Meta:
        verbose_name = "Sesja obliczania śladu węglowego"
        verbose_name_plural = "Sesje obliczeń śladu węglowego"
        ordering = ['-calculated_at']

    def __str__(self):
        if self.user:
            return f"Obliczenie dla {self.user.username} z dnia {self.calculated_at.strftime('%Y-%m-%d %H:%M')}"
        return f"Anonimowe obliczenie ({self.session_key}) z dnia {self.calculated_at.strftime('%Y-%m-%d %H:%M')}"

class ReductionTip(models.Model):
    title = models.CharField(max_length=255, verbose_name="Tytuł porady")
    description_template = models.TextField(
        verbose_name="Szablon opisu porady",
        help_text='Użyj placeholderów: {{user_input_X}} dla wartości czynnika X, {{annual_emission_category_Y}} dla emisji w kategorii Y, {{potential_annual_savings_kg}} dla szacowanych oszczędności.'
    )
    trigger_conditions_json = models.JSONField(
        verbose_name="Warunki wyświetlania porady (JSON)",
        null=True, blank=True,
        help_text="Określa, kiedy porada jest odpowiednia. Jeśli puste, porada wyświetlana jest zawsze (jeśli aktywna)."
    )
    estimated_co2_reduction_kg_annual_logic = models.JSONField(
        null=True, blank=True,
        verbose_name="Logika szacowania rocznego ograniczenia CO2 (JSON)"
    )
    priority = models.PositiveIntegerField(default=0, verbose_name="Priorytet (im wyższy, tym ważniejszy)")
    suggested_products = models.ManyToManyField(
        Product,
        blank=True,
        verbose_name="Sugerowane produkty EcoMarket",
        related_name="reduction_tips"
    )
    applies_to_categories = models.ManyToManyField(
        ActivityCategory,
        blank=True,
        verbose_name="Dotyczy kategorii aktywności",
        help_text="Jeśli określono, porada będzie wyświetlana, jeśli są emisje w tych kategoriach (można doprecyzować w trigger_conditions_json)"
    )
    external_link_url = models.URLField(blank=True, null=True, verbose_name="Zewnętrzny link (do artykułu, źródła)")
    external_link_text = models.CharField(max_length=200, blank=True, null=True, verbose_name="Tekst do zewnętrznego linku")
    icon_class = models.CharField(max_length=50, blank=True, null=True, verbose_name="Klasa ikony do porady")
    is_active = models.BooleanField(default=True, verbose_name="Porada aktywna")

    class Meta:
        verbose_name = "Porada redukująca ślad"
        verbose_name_plural = "Porady redukujące ślad"
        ordering = ['-priority', 'title']

    def __str__(self):
        return self.title