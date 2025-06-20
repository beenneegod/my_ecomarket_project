# carbon_calculator/models.py
from django.db import models
from django.conf import settings
from store.models import Product # Убедитесь, что модель Product доступна для импорта
from django.utils.text import slugify
from django.core.exceptions import ValidationError

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
        help_text='Dla "select": {"option_value1": "Etykieta opcji 1", "option_value2": "Etykieta opcji 2"}. Wartość to mnożnik dla co2_kg_per_unit lub wartość do obliczeń.'
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

    class Meta:
        verbose_name = "Współczynnik emisji"
        verbose_name_plural = "Współczynniki emisji"
        ordering = ['activity_category__order', 'activity_category__name', 'order', 'name']

    def __str__(self):
        return f"{self.name} ({self.activity_category.name})"

    def clean(self):
        super().clean()
        # Валидация form_field_options
        if self.form_field_type == 'select' and self.form_field_options:
            if not isinstance(self.form_field_options, dict):
                raise ValidationError({'form_field_options': 'form_field_options должен быть словарём (dict).'} )
            for k, v in self.form_field_options.items():
                if not isinstance(k, str):
                    raise ValidationError({'form_field_options': 'Ключи в form_field_options должны быть строками.'})
                if not (isinstance(v, (str, int, float))):
                    raise ValidationError({'form_field_options': 'Значения в form_field_options должны быть строками или числами.'})
        # Валидация periodicity_options_for_form
        if self.periodicity_options_for_form:
            if not isinstance(self.periodicity_options_for_form, dict):
                raise ValidationError({'periodicity_options_for_form': 'periodicity_options_for_form должен быть словарём (dict).'})
            for k, v in self.periodicity_options_for_form.items():
                if not isinstance(k, str):
                    raise ValidationError({'periodicity_options_for_form': 'Ключи в periodicity_options_for_form должны быть строками.'})
                if not isinstance(v, dict):
                    raise ValidationError({'periodicity_options_for_form': 'Значения в periodicity_options_for_form должны быть словарями.'})
                if 'label' not in v or 'annual_multiplier' not in v:
                    raise ValidationError({'periodicity_options_for_form': 'Каждый элемент должен содержать label и annual_multiplier.'})

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