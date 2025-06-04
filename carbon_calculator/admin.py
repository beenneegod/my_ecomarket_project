# carbon_calculator/admin.py
from django.contrib import admin
from .models import ActivityCategory, EmissionFactor, UserFootprintSession, ReductionTip
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
    list_display = ('name', 'activity_category', 'unit_name', 'co2_kg_per_unit', 'form_field_type', 'is_active', 'order')
    list_filter = ('activity_category', 'is_active', 'form_field_type')
    search_fields = ('name', 'form_question_text', 'activity_category__name', 'data_source_info')
    list_editable = ('co2_kg_per_unit', 'is_active', 'order', 'form_field_type')
    fieldsets = (
        (None, {
            'fields': ('activity_category', 'name', 'description', 'is_active', 'order')
        }),
        ('Данные для расчета CO2', {
            'fields': ('unit_name', 'co2_kg_per_unit', 'data_source_info', ('valid_from', 'valid_to'))
        }),
        ('Настройки поля в форме калькулятора', {
            'classes': ('collapse',),
            'fields': ('form_question_text', 'form_field_type', 'form_field_options', 'form_placeholder', 'form_help_text', 'periodicity_options_for_form'),
        }),
    )
    ordering = ('activity_category__order', 'order')
    save_as = True # Удобно для создания похожих факторов

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
            'fields': ('title', 'description_template', 'is_active', 'priority', 'icon_class')
        }),
        ('Warunki i zastosowanie', {
            'fields': ('applies_to_categories', 'trigger_conditions_json')
        }),
        ('Obliczanie oszczędności i produkty', {
            'fields': ('estimated_co2_reduction_kg_annual_logic', 'suggested_products')
        }),
        ('Informacje zewnętrzne', {
            'fields': ('external_link_url', 'external_link_text')
        }),
    )
    ordering = ('-priority', 'title')

    @admin.display(description="Dotyczy kategorii")
    def categories_display(self, obj):
        return ", ".join([cat.name for cat in obj.applies_to_categories.all()])