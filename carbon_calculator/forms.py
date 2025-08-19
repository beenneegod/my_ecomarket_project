# carbon_calculator/forms.py
from django import forms
from .models import EmissionFactor, ActivityCategory
from decimal import Decimal

class FootprintCalculatorForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Группируем активные факторы по категориям и сортируем
        self.grouped_factors = {}
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
                
                # Основное поле для ввода значения
                if factor.form_field_type == 'number':
                    self.fields[field_name_base] = forms.DecimalField(
                        label=factor.form_question_text,
                        help_text=factor.form_help_text,
                        required=False,
                        min_value=Decimal('0.0'),
                        widget=forms.NumberInput(attrs={
                            'class': 'form-control form-control-sm',
                            'placeholder': factor.form_placeholder or factor.unit_name
                        })
                    )
                elif factor.form_field_type == 'select' and factor.form_field_options:
                    choices = [(key, label) for key, label in factor.form_field_options.items()]
                    # Добавляем пустой выбор, если опции не обязательны
                    # (можно сделать required=True, если выбор всегда нужен)
                    choices.insert(0, ('', 'Wybierz')) 
                    self.fields[field_name_base] = forms.ChoiceField(
                        label=factor.form_question_text,
                        help_text=factor.form_help_text,
                        choices=choices,
                        required=False,
                        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
                    )
                # Добавьте другие типы полей (radio, checkbox), если необходимо

                # Дополнительное поле для выбора периодичности, если определено
                if factor.periodicity_options_for_form:
                    period_choices = [
                        (key, details.get('label', key)) 
                        for key, details in factor.periodicity_options_for_form.items()
                    ]
                    # Можно добавить значение по умолчанию или сделать обязательным
                    period_choices.insert(0, ('', 'Wybierz okres'))
                    self.fields[f'{field_name_base}_period'] = forms.ChoiceField(
                        label=f"Częstotliwość dla '{factor.name}'", # Lub bardziej przyjazny label
                        choices=period_choices,
                        required=False, # Зависит от того, всегда ли нужна периодичность
                        widget=forms.Select(attrs={'class': 'form-select form-select-sm mt-1'})
                    )
                
                # Сохраняем сам фактор для удобства в шаблоне
                self.fields[field_name_base].factor_instance = factor
                if f'{field_name_base}_period' in self.fields:
                     self.fields[f'{field_name_base}_period'].factor_instance = factor # Связываем и с полем периода
                
                self.grouped_factors[category].append({
                    'main_field': self.fields[field_name_base],
                    'main_field_name': field_name_base,
                    'period_field': self.fields.get(f'{field_name_base}_period'),
                    'period_field_name': f'{field_name_base}_period' if f'{field_name_base}_period' in self.fields else None,
                    'factor': factor # Для прямого доступа к атрибутам фактора в шаблоне
                })
    
    def clean(self):
        cleaned_data = super().clean()
        # Пример валидации: если выбрана периодичность, то и значение должно быть введено
        for field_name, value in cleaned_data.items():
            if field_name.endswith('_period') and value: # Если поле периода заполнено
                base_field_name = field_name.replace('_period', '')
                if not cleaned_data.get(base_field_name):
                    self.add_error(base_field_name, "Proszę podać wartość, ponieważ wybrano częstotliwość.")
                    self.add_error(field_name, "") # Оznaczamy również pole okresу jako błędne (без текста)
        
        # Проверка, что хотя бы одно поле с основным значением заполнено
        has_input = any(
            value for key, value in cleaned_data.items() 
            if key.startswith('factor_input_') and not key.endswith('_period') and value is not None
        )
        if not has_input:
            raise forms.ValidationError(
                "Proszę wprowadzić dane przynajmniej dla jednej aktywności, aby obliczyć swój ślad węglowy.",
                code='no_input'
            )
            
        return cleaned_data