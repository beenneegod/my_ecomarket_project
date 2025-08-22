# carbon_calculator/forms.py
from django import forms
from .models import EmissionFactor, ActivityCategory, Region
from decimal import Decimal

class FootprintCalculatorForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Krok 1: Profil
        regions = Region.objects.all().order_by('name')
        region_choices = [(str(r.id), f"{r.name} ({r.grid_intensity_kg_per_kwh} kg/kWh)") for r in regions]
        default_region = Region.objects.filter(is_default=True).first()
        if region_choices:
            self.fields['profile_region'] = forms.ChoiceField(
                label="Twój region/kraj (dla energii elektrycznej)",
                choices=[('', 'Wybierz region')] + region_choices,
                required=False,
                initial=str(default_region.id) if default_region else '',
                widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
            )
        self.fields['profile_household_members'] = forms.IntegerField(
            label="Liczba osób w gospodarstwie domowym",
            required=False,
            min_value=1,
            widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'np. 3'})
        )

    # Grupujemy pola w sekcje
        self.grouped_factors = {}
        self.profile_section = ['profile_region', 'profile_household_members']
        categories = ActivityCategory.objects.filter(factors__is_active=True).distinct().order_by('order', 'name')

        for category in categories:
            factors_in_category = EmissionFactor.objects.filter(
                activity_category=category,
                is_active=True
            ).order_by('order', 'name')

            if not factors_in_category.exists():
                continue

            self.grouped_factors[category] = []

            for factor in factors_in_category:
                field_name_base = f'factor_input_{factor.id}'

                # Główne pole do wprowadzania wartości
                if factor.form_field_type == 'number':
                    self.fields[field_name_base] = forms.DecimalField(
                        label=factor.form_question_text,
                        help_text=factor.form_help_text,
                        required=False,
                        min_value=factor.min_reasonable_value if factor.min_reasonable_value is not None else Decimal('0.0'),
                        max_value=factor.max_reasonable_value if factor.max_reasonable_value is not None else None,
                        widget=forms.NumberInput(attrs={
                            'class': 'form-control form-control-sm',
                            'placeholder': factor.form_placeholder or factor.unit_name
                        })
                    )
                elif factor.form_field_type == 'select' and factor.form_field_options:
                    choices = [(key, label) for key, label in factor.form_field_options.items()]
                    # Dodajemy pustą opcję, jeśli wybór nie jest wymagany
                    # (można ustawić required=True, jeśli wybór jest zawsze potrzebny)
                    choices.insert(0, ('', 'Wybierz'))
                    self.fields[field_name_base] = forms.ChoiceField(
                        label=factor.form_question_text,
                        help_text=factor.form_help_text,
                        choices=choices,
                        required=False,
                        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
                    )
                # Dodatkowe pole wyboru okresu, jeśli zdefiniowane
                if factor.periodicity_options_for_form:
                    period_choices = [
                        (key, details.get('label', key))
                        for key, details in factor.periodicity_options_for_form.items()
                    ]
                    # Można dodać wartość domyślną lub ustawić jako wymagane
                    period_choices.insert(0, ('', 'Wybierz okres'))
                    self.fields[f'{field_name_base}_period'] = forms.ChoiceField(
                        label=f"Okres dla „{factor.name}”",
                        choices=period_choices,
                        required=False,  # Zależy od tego, czy okres jest zawsze wymagany
                        widget=forms.Select(attrs={'class': 'form-select form-select-sm mt-1'})
                    )

                # Przechowujemy obiekt czynnika dla wygody w szablonie
                self.fields[field_name_base].factor_instance = factor
                if f'{field_name_base}_period' in self.fields:
                    self.fields[f'{field_name_base}_period'].factor_instance = factor  # Powiązanie również z polem okresu

                self.grouped_factors[category].append({
                    'main_field': self.fields[field_name_base],
                    'main_field_name': field_name_base,
                    'period_field': self.fields.get(f'{field_name_base}_period'),
                    'period_field_name': f'{field_name_base}_period' if f'{field_name_base}_period' in self.fields else None,
                    'factor': factor  # Dla bezpośredniego dostępu do atrybutów czynnika w szablonie
                })
    
    def clean(self):
        cleaned_data = super().clean()
        # Walidacja przykładowa: jeśli wybrano okres, musi być podana wartość
        for field_name, value in cleaned_data.items():
            if field_name.endswith('_period') and value:  # Jeśli pole okresu jest wypełnione
                base_field_name = field_name.replace('_period', '')
                if not cleaned_data.get(base_field_name):
                    self.add_error(base_field_name, "Podaj wartość, ponieważ wybrano okres.")
                    self.add_error(field_name, "")  # Oznaczamy również pole okresu jako błędne (bez tekstu)

        # Sprawdzenie, że przynajmniej jedno pole z wartością jest wypełnione
        has_input = any(
            value for key, value in cleaned_data.items()
            if key.startswith('factor_input_') and not key.endswith('_period') and value is not None
        )
        if not has_input:
            raise forms.ValidationError(
                "Wypełnij co najmniej jedno pole, aby obliczyć swój ślad węglowy.",
                code='no_input'
            )

        # Miękkie ostrzeżenia: jeśli wartość jest poza rozsądnymi granicami
        # Nie blokuje wysyłki — dodaje ostrzeżenie do pola
        for name, field in self.fields.items():
            if not name.startswith('factor_input_') or name.endswith('_period'):
                continue
            factor = getattr(field, 'factor_instance', None)
            if not factor:
                continue
            val = cleaned_data.get(name)
            if val is None:
                continue
            try:
                val_dec = Decimal(str(val))
            except Exception:
                continue
            # Jeśli ustawiono min/max i wartość wychodzi poza granice — dodaj ostrzeżenie
            if factor.min_reasonable_value is not None and val_dec < factor.min_reasonable_value:
                self.add_error(name, forms.ValidationError(
                    f"Wartość poniżej minimalnie rozsądnej ({factor.min_reasonable_value}). Proszę sprawdzić.",
                    code='below_reasonable_min'
                ))
            if factor.max_reasonable_value is not None and val_dec > factor.max_reasonable_value:
                self.add_error(name, forms.ValidationError(
                    f"Wartość powyżej maksymalnie rozsądnej ({factor.max_reasonable_value}). Proszę sprawdzić.",
                    code='above_reasonable_max'
                ))

        return cleaned_data