# carbon_calculator/admin.py
from django.contrib import admin
from .models import ActivityCategory, EmissionFactor, UserFootprintSession, ReductionTip
from .models import Region
from django.utils.html import format_html # Для отображения JSON в админке
import json

@admin.register(ActivityCategory)
class ActivityCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order', 'description_short', 'icon_class')
    list_editable = ('order', 'icon_class')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'description')

    @admin.display(description="Krótki opis")
    def description_short(self, obj):
        if obj.description:
            return (obj.description[:75] + '...') if len(obj.description) > 75 else obj.description
        return "-"

@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ('name', 'activity_category', 'unit_name', 'co2_kg_per_unit', 'use_region_grid_intensity', 'form_field_type', 'is_active', 'order')
    list_filter = ('activity_category', 'is_active', 'form_field_type')
    list_filter = ('activity_category', 'is_active', 'form_field_type', 'use_region_grid_intensity')
    search_fields = ('name', 'form_question_text', 'activity_category__name', 'data_source_info')
    list_editable = ('co2_kg_per_unit', 'is_active', 'order', 'form_field_type')
    fieldsets = (
        (None, {
            'fields': ('activity_category', 'name', 'description', 'is_active', 'order')
        }),
        ('Дane для расчета CO2', {
            'fields': ('unit_name', 'co2_kg_per_unit', 'use_region_grid_intensity', 'data_source_info', ('valid_from', 'valid_to'))
        }),
        ('Настройки поля в форме калькулятора', {
            'classes': ('collapse',),
            'fields': ('form_question_text', 'form_field_type', 'form_field_options', 'form_placeholder', 'form_help_text', 'periodicity_options_for_form'),
        }),
    )
    ordering = ('activity_category__order', 'order')
    save_as = True # Удобно для создания похожих факторов


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "grid_intensity_kg_per_kwh", "is_default")
    list_editable = ("grid_intensity_kg_per_kwh", "is_default")
    search_fields = ("name", "code")

@admin.register(UserFootprintSession)
class UserFootprintSessionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user_display', 'total_co2_emissions_kg_annual', 'calculated_at', 'calculation_version')
    list_filter = ('calculated_at', 'calculation_version')
    search_fields = ('user__username', 'session_key', 'inputs_data') # Поиск по JSON может быть медленным
    readonly_fields = (
        'user', 'session_key', 'inputs_data_formatted', 
        'total_co2_emissions_kg_annual', 'category_breakdown_kg_annual_formatted', 
        'calculated_at', 'calculation_version'
    )
    exclude = ('inputs_data', 'category_breakdown_kg_annual') # Скрываем сырые JSON, показываем отформатированные

    @admin.display(description="Użytkownik")
    def user_display(self, obj):
        return obj.user.username if obj.user else "Anonimowy"

    @admin.display(description="Wprowadzone dane")
    def inputs_data_formatted(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.inputs_data, indent=2, ensure_ascii=False))

    @admin.display(description="Podział na kategorie (kg CO2, rok)")
    def category_breakdown_kg_annual_formatted(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.category_breakdown_kg_annual, indent=2, ensure_ascii=False))

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None): # Tylko podgląd
        return False

    def has_delete_permission(self, request, obj=None): # Można zezwolić na usuwanie w razie potrzeby
        return super().has_delete_permission(request, obj)


@admin.register(ReductionTip)
class ReductionTipAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'priority', 'categories_display')
    list_filter = ('is_active', 'applies_to_categories')
    search_fields = ('title', 'description_template')
    list_editable = ('is_active', 'priority')
    filter_horizontal = ('suggested_products', 'applies_to_categories')
    fieldsets = (
        (None, {
            'fields': ('title', 'description_template', 'is_active', 'priority', 'icon_class'),
            'description': (
                '<b>Przykłady description_template dla ReductionTip:</b><br>'
                '<pre>'
                'Przykład 1 (mięso, ID=7):\n'
                'Wy wskazaliście, że spożywacie czerwone mięso {{user_input_raw_7}} {{user_input_unit_label_7}}.\n'
                'To daje około {{user_input_annual_co2_7}} kg CO2-ekw. rocznie.\n'
                'Spróbuj zastąpić część dań mięsnych roślinnymi alternatywami.\n'
                'To może zmniejszyć Twój ślad o {{potential_annual_savings_kg}} kg CO2 rocznie.\n'
                'Kategoria "Żywność" ({{annual_emission_category_name_food}}) stanowi {{category_percentage_food}}% Twojego całkowitego śladu: {{total_annual_emissions_kg}} kg.\n\n'
                'Przykład 2 (energia domowa, kategoria dom-energia):\n'
                'Twoje emisje z domowego zużycia energii (kategoria {{annual_emission_category_name_dom-energia}}) wynoszą {{annual_emission_category_dom-energia}} kg CO2-ekw. rocznie.\n'
                'Zastosowanie energooszczędnych żarówek może zaoszczędzić do {{potential_annual_savings_kg}} kg CO2 rocznie.'
                '</pre>'
            )
        }),
        ('Warunki i zastosowanie', {
            'fields': ('applies_to_categories', 'trigger_conditions_json'),
            'description': (
                '<b>Przykłady JSON dla trigger_conditions_json:</b><br>'
                '<pre>'
                'Przykład 1 (Pokaż wskazówkę, jeśli emisje z żywności > 300 kg/rok):\n'
                '[\n'
                '    {\n'
                '        "type": "category_emission_gt",\n'
                '        "category_slug": "pitanie",\n'
                '        "threshold_kg_annual": 300.0\n'
                '    }\n'
                ']\n\n'
                'Przykład 2 (Pokaż wskazówkę, jeśli użytkownik wybrał dla czynnika o ID=10 opcję "codziennie"):\n'
                '[\n'
                '    {\n'
                '        "type": "input_value_equals",\n'
                '        "factor_id": 10,\n'
                '        "expected_value": "daily"\n'
                '    }\n'
                ']\n\n'
                'Przykład 3 (Pokaż, jeśli emisje z transportu > 20% całkowitego śladu):\n'
                '[\n'
                '    {\n'
                '        "type": "category_emission_percentage_gt",\n'
                '        "category_slug": "transport",\n'
                '        "percentage": 20\n'
                '    }\n'
                ']'
                '</pre>'
            )
        }),
        ('Obliczanie oszczędności i produkty', {
            'fields': ('estimated_co2_reduction_kg_annual_logic', 'suggested_products'),
            'description': (
                '<b>Przykłady JSON dla estimated_co2_reduction_kg_annual_logic:</b><br>'
                '<pre>'
                'Przykład 1: Stała oszczędność\n'
                'Wskazówka: "Zawsze wyłączaj światło wychodząc z pokoju."\n'
                '{"type": "fixed", "value_kg_annual": 20.0}\n\n'
                'Przykład 2: Procent od emisji kategorii "dom-energia"\n'
                'Wskazówka: "Obniż temperaturę ogrzewania o 1 stopień."\n'
                '{"type": "percentage_of_category", "category_slug": "dom-energia", "percentage": 5}\n\n'
                'Przykład 3: Redukcja o 10% emisji z czynnika o ID=12\n'
                'Wskazówka: "Wymień żarówki na LED."\n'
                '{"type": "reduction_from_input", "input_factor_id": 12, "reduction_percentage": 10}\n\n'
                'Przykład 4: Zamiana 50% podróży autem (ID=5, CO2/km=0.18) na rower (CO2/km=0)\n'
                'Wskazówka: "Częściej używaj roweru zamiast samochodu na krótkich trasach."\n'
                '{\n'
                '    "type": "activity_substitution",\n'
                '    "original_input_factor_id": 5,\n'
                '    "alternative_co2_per_unit": 0.0,\n'
                '    "affected_input_percentage": 50\n'
                '}\n\n'
                'Przykład 5: Ustaw wartość czynnika na 0 (np. całkowita rezygnacja z produktu, ID=15)\n'
                'Wskazówka: "Całkowicie zrezygnuj z produktu X."\n'
                '{"type": "direct_from_input_change", "input_factor_id": 15, "new_value_for_input": 0}'
                '</pre>'
            )
        }),
        ('Informacje zewnętrzne', {
            'fields': ('external_link_url', 'external_link_text')
        }),
    )
    ordering = ('-priority', 'title')

    @admin.display(description="Dotyczy kategorii")
    def categories_display(self, obj):
        return ", ".join([cat.name for cat in obj.applies_to_categories.all()])