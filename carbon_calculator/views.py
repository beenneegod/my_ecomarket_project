# carbon_calculator/views.py
from django.shortcuts import render
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from .forms import FootprintCalculatorForm
from .models import EmissionFactor, UserFootprintSession, ReductionTip, ActivityCategory, Region
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
import random
from django.conf import settings as django_settings
from django.utils.html import escape # Для безопасной подстановки

logger = logging.getLogger(__name__)

def check_tip_conditions(tip_conditions_json, user_inputs_db, category_breakdown_calc, total_annual_emissions_calc, active_factors_map):
    """
    Проверяет, выполняются ли условия для показа совета.
    :param tip_conditions_json: JSON-поле trigger_conditions_json из ReductionTip
    :param user_inputs_db: Словарь user_inputs_for_session_db (введенные пользователем данные)
                           Структура: { "factor_id_X": {"raw_value": Y, "chosen_period_key_if_any": Z, ...}, ...}
    :param category_breakdown_calc: Словарь category_breakdown_kg_annual_calc {category_slug: Decimal(value)}
    :param total_annual_emissions_calc: Decimal, общий годовой след
    :param active_factors_map: Словарь {factor_id: factor_instance} (для доступа к деталям факторов)
    :return: True, если все условия выполнены (или нет условий), иначе False
    """
    if not tip_conditions_json:
        return True # Если нет условий, совет считается применимым по умолчанию

    if not isinstance(tip_conditions_json, list):
        logger.warning(f"trigger_conditions_json не является списком: {tip_conditions_json} для совета.")
        return False # Некорректный формат условий

    for condition in tip_conditions_json:
        if not isinstance(condition, dict):
            logger.warning(f"Элемент условия не является словарем: {condition} для совета.")
            return False # Пропускаем некорректное условие, считая, что общее условие не выполнено

        condition_type = condition.get("type")
        current_condition_met = False # Флаг для текущего проверяемого условия

        try:
            if condition_type == "category_emission_gt":
                cat_slug = condition.get("category_slug")
                threshold = Decimal(str(condition.get("threshold_kg_annual", "0")))
                if cat_slug and cat_slug in category_breakdown_calc and category_breakdown_calc[cat_slug] > threshold:
                    current_condition_met = True
            
            elif condition_type == "category_emission_lt":
                cat_slug = condition.get("category_slug")
                threshold = Decimal(str(condition.get("threshold_kg_annual", "999999999"))) # Большое значение по умолчанию
                # Если категории нет в расчете, ее выбросы = 0, что меньше порога
                category_emission = category_breakdown_calc.get(cat_slug, Decimal('0'))
                if cat_slug and category_emission < threshold:
                    current_condition_met = True

            elif condition_type == "category_emission_percentage_gt":
                cat_slug = condition.get("category_slug")
                threshold_percentage = Decimal(str(condition.get("percentage", "0")))
                if total_annual_emissions_calc > Decimal('0') and cat_slug and cat_slug in category_breakdown_calc:
                    category_emission_value = category_breakdown_calc[cat_slug]
                    category_percentage = (category_emission_value / total_annual_emissions_calc) * Decimal('100')
                    if category_percentage > threshold_percentage:
                        current_condition_met = True
            
            elif condition_type == "input_value_gt":
                factor_id_str = str(condition.get("factor_id"))
                threshold_input_val = Decimal(str(condition.get("threshold_value", "0")))
                if factor_id_str in user_inputs_db:
                    # Сравниваем сырое значение, введенное пользователем
                    raw_value = user_inputs_db[factor_id_str].get("raw_value")
                    if raw_value is not None and Decimal(str(raw_value)) > threshold_input_val:
                        current_condition_met = True
            
            elif condition_type == "input_value_equals":
                factor_id_str = str(condition.get("factor_id"))
                expected_val_str = str(condition.get("expected_value")) # Ожидаем строку, т.к. опции select - строки
                if factor_id_str in user_inputs_db:
                    # Для полей 'select', user_inputs_db[factor_id_str]["raw_value"] будет строковым ключом опции
                    # Для числовых полей это будет число, но мы сравниваем как строки для универсальности
                    raw_value = user_inputs_db[factor_id_str].get("raw_value")
                    if raw_value is not None and str(raw_value) == expected_val_str:
                        current_condition_met = True

            elif condition_type == "total_emission_gt":
                threshold_total = Decimal(str(condition.get("threshold_kg_annual", "0")))
                if total_annual_emissions_calc > threshold_total:
                    current_condition_met = True

            # Добавьте сюда другие типы условий по мере необходимости...

            else:
                logger.warning(f"Неизвестный или неполный тип условия '{condition_type}' в: {condition} для совета.")
                return False # Если встретили неизвестное условие, считаем, что общее условие не выполнено

            if not current_condition_met: # Если текущее условие из списка не выполнено (для логики "И")
                return False # Прекращаем проверку, т.к. не все условия выполнены

        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Ошибка при обработке JSON-условия {condition} для совета: {e}")
            return False # Считаем условие невыполненным при любой ошибке в его обработке
            
    return True # Если все условия в списке были успешно проверены и выполнены

def calculate_tip_savings(tip_savings_logic_json, user_inputs_db, category_breakdown_calc, total_annual_emissions_calc, active_factors_map):
    """
    Рассчитывает потенциальную экономию CO2 для совета.
    :param tip_savings_logic_json: JSON-поле estimated_co2_reduction_kg_annual_logic
    :param user_inputs_db: Словарь user_inputs_for_session_db 
                           Структура: { "factor_id_X": {"raw_value": Y, "annual_multiplier_used": Z, 
                                                       "calculated_annual_co2_for_this_input": C, ...}, ...}
    :param category_breakdown_calc: Словарь category_breakdown_kg_annual_calc {category_slug: Decimal(value)}
    :param total_annual_emissions_calc: Decimal, общий годовой след
    :param active_factors_map: Словарь {factor_id: factor_instance} (для доступа к co2_kg_per_unit)
    :return: Decimal (экономия в кг CO2/год) или None
    """
    if not tip_savings_logic_json or not isinstance(tip_savings_logic_json, dict):
        logger.debug(f"Логика расчета экономии отсутствует или имеет неверный формат: {tip_savings_logic_json}")
        return None

    savings_type = tip_savings_logic_json.get("type")
    potential_savings = None
    quantizer = Decimal('0.1') # Округляем до 1 знака после запятой

    try:
        if savings_type == "fixed":
            value_str = str(tip_savings_logic_json.get("value_kg_annual", "0"))
            potential_savings = Decimal(value_str)
            logger.debug(f"Расчет экономии (fixed): {potential_savings} кг/год")
        
        elif savings_type == "percentage_of_category":
            cat_slug = tip_savings_logic_json.get("category_slug")
            percentage_str = str(tip_savings_logic_json.get("percentage", "0"))
            percentage = Decimal(percentage_str)
            
            if cat_slug in category_breakdown_calc and percentage > 0:
                category_emission = category_breakdown_calc[cat_slug]
                potential_savings = (category_emission * percentage / Decimal('100'))
                logger.debug(f"Расчет экономии (percentage_of_category '{cat_slug}'): {category_emission} * {percentage}% = {potential_savings} кг/год")
            else:
                logger.debug(f"Категория '{cat_slug}' не найдена в выбросах или процент равен 0 для percentage_of_category.")

        elif savings_type == "reduction_from_input":
            # Экономия = X% от годовых выбросов, связанных с конкретным пользовательским вводом
            input_factor_id_str = str(tip_savings_logic_json.get("input_factor_id"))
            reduction_percentage_str = str(tip_savings_logic_json.get("reduction_percentage", "0"))
            reduction_percentage = Decimal(reduction_percentage_str)
            
            if input_factor_id_str in user_inputs_db and reduction_percentage > 0:
                input_details = user_inputs_db[input_factor_id_str]
                # Используем уже рассчитанные годовые выбросы для этого ввода
                annual_co2_for_this_input = Decimal(str(input_details.get("calculated_annual_co2_for_this_input", "0")))
                potential_savings = annual_co2_for_this_input * reduction_percentage / Decimal('100')
                logger.debug(f"Расчет экономии (reduction_from_input factor_id={input_factor_id_str}): {annual_co2_for_this_input} * {reduction_percentage}% = {potential_savings} кг/год")
            else:
                logger.debug(f"Фактор ID {input_factor_id_str} не найден во вводе или процент равен 0 для reduction_from_input.")

        elif savings_type == "activity_substitution":
            # Замена X% одной активности (с оригинальным CO2/ед.) на альтернативную (с новым CO2/ед.)
            orig_factor_id_str = str(tip_savings_logic_json.get("original_input_factor_id"))
            # CO2 на единицу альтернативной активности
            alt_co2_per_unit_str = str(tip_savings_logic_json.get("alternative_co2_per_unit", "0"))
            alt_co2_per_unit = Decimal(alt_co2_per_unit_str)
            # Какой процент оригинальной активности заменяется (по умолчанию 100%)
            affected_input_percentage_str = str(tip_savings_logic_json.get("affected_input_percentage", "100"))
            affected_input_percentage = Decimal(affected_input_percentage_str)

            if orig_factor_id_str in user_inputs_db and affected_input_percentage > 0:
                original_input_details = user_inputs_db[orig_factor_id_str]
                original_factor_instance = active_factors_map.get(int(orig_factor_id_str))

                if original_factor_instance:
                    # Годовое количество единиц оригинальной активности (например, годовой пробег)
                    raw_value = Decimal(str(original_input_details.get("raw_value", "0")))
                    annual_multiplier = Decimal(str(original_input_details.get("annual_multiplier_used", "1")))
                    annual_units_of_activity = raw_value * annual_multiplier
                    
                    # Единицы активности, которые подвергаются замене
                    units_to_substitute = annual_units_of_activity * (affected_input_percentage / Decimal('100'))

                    # Исходные выбросы от заменяемой части
                    original_emissions_from_substituted_part = units_to_substitute * original_factor_instance.co2_kg_per_unit
                    
                    # Выбросы от альтернативной активности для той же части
                    alternative_emissions_from_substituted_part = units_to_substitute * alt_co2_per_unit
                                                          
                    potential_savings = original_emissions_from_substituted_part - alternative_emissions_from_substituted_part
                    logger.debug(f"Расчет экономии (activity_substitution factor_id={orig_factor_id_str}): Savings={potential_savings} кг/год")
                else:
                    logger.warning(f"Оригинальный фактор ID {orig_factor_id_str} не найден в active_factors_map для activity_substitution.")
            else:
                logger.debug(f"Фактор ID {orig_factor_id_str} не найден во вводе или процент равен 0 для activity_substitution.")
        
        elif savings_type == "direct_from_input_change":
            # Предполагаем, что совет предлагает изменить значение конкретного фактора на новое
            input_factor_id_str = str(tip_savings_logic_json.get("input_factor_id"))
            new_value_for_input_str = str(tip_savings_logic_json.get("new_value_for_input", "0"))
            new_value_for_input = Decimal(new_value_for_input_str)
            
            # Периодичность для нового значения (если отличается от исходной или если исходная не указана)
            # Если period_key_for_new_value не указан, используется annual_multiplier_used из исходного ввода
            new_period_key = tip_savings_logic_json.get("period_key_for_new_value")

            if input_factor_id_str in user_inputs_db:
                original_input_details = user_inputs_db[input_factor_id_str]
                factor_instance = active_factors_map.get(int(input_factor_id_str))

                if factor_instance:
                    # Исходные годовые выбросы для этого фактора
                    original_annual_co2_for_input = Decimal(str(original_input_details.get("calculated_annual_co2_for_this_input", "0")))
                    
                    # Рассчитываем новые годовые выбросы
                    new_annual_multiplier = Decimal(str(original_input_details.get("annual_multiplier_used", "1"))) # По умолчанию
                    if new_period_key and getattr(factor_instance, 'periodicity_options_for_form', None):
                        period_details = factor_instance.periodicity_options_for_form.get(new_period_key)
                        if period_details and 'annual_multiplier' in period_details:
                            new_annual_multiplier = Decimal(str(period_details['annual_multiplier']))
                    
                    new_annual_co2_for_input = (new_value_for_input * new_annual_multiplier * factor_instance.co2_kg_per_unit)
                    
                    potential_savings = original_annual_co2_for_input - new_annual_co2_for_input
                    logger.debug(f"Расчет экономии (direct_from_input_change factor_id={input_factor_id_str}): Original CO2={original_annual_co2_for_input}, New CO2={new_annual_co2_for_input}. Savings={potential_savings} кг/год")
            else:
                logger.debug(f"Фактор ID {input_factor_id_str} не найден во вводе для direct_from_input_change.")
        
        else:
            logger.warning(f"Неизвестный тип логики расчета экономии: '{savings_type}' для совета.")

        if potential_savings is not None:
            # Экономия не может быть отрицательной (т.е. совет не должен увеличивать след)
            return max(Decimal('0.0'), potential_savings.quantize(quantizer, ROUND_HALF_UP))

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Ошибка приведения типов или доступа по ключу при расчете экономии (логика: {tip_savings_logic_json}): {e}")
    except Exception as e_global:
        logger.error(f"Непредвиденная ошибка при расчете экономии для совета (логика: {tip_savings_logic_json}): {e_global}")
    
    return None

def format_tip_description(description_template, user_inputs_db, tip_calculated_savings_kg, 
                           category_breakdown_calc, total_annual_emissions_calc, 
                           active_factors_map):
    """
    Форматирует шаблон описания совета, подставляя значения.
    """
    if not description_template:
        return ""
        
    formatted_text = str(description_template) # Убедимся, что работаем со строкой

    # 1. Подстановка потенциальной экономии
    if tip_calculated_savings_kg is not None:
        formatted_text = formatted_text.replace("{{potential_annual_savings_kg}}", escape(str(tip_calculated_savings_kg)))
    else: # Если экономия не рассчитана, можно заменить на прочерк или удалить плейсхолдер
        formatted_text = formatted_text.replace("{{potential_annual_savings_kg}}", "не оценено")

    # 2. Подстановка значений пользовательского ввода
    # Плейсхолдеры:
    # {{user_input_raw_X}} - сырое значение для фактора X
    # {{user_input_unit_label_X}} - единица измерения для сырого значения фактора X
    # {{user_input_annual_co2_X}} - годовые выбросы CO2 от фактора X
    # {{user_input_annual_units_X}} - годовое количество единиц для фактора X (сырое значение * годовой множитель)
    # {{factor_name_X}} - название фактора X
    # {{factor_question_X}} - текст вопроса для фактора X
    
    for factor_id_str_placeholder in list(user_inputs_db.keys()) + [str(f_id) for f_id in active_factors_map.keys()]: # Чтобы покрыть и те факторы, по которым не было ввода
        details = user_inputs_db.get(factor_id_str_placeholder)
        factor_instance = active_factors_map.get(int(factor_id_str_placeholder))

        if factor_instance: # Имя и вопрос фактора доступны всегда, если фактор существует
            formatted_text = formatted_text.replace(f"{{{{factor_name_{factor_id_str_placeholder}}}}}", escape(factor_instance.name))
            formatted_text = formatted_text.replace(f"{{{{factor_question_{factor_id_str_placeholder}}}}}", escape(factor_instance.form_question_text))

        if details: # Если был ввод по этому фактору
            raw_value = details.get("raw_value", "")
            unit_label = details.get("input_unit_label", "")
            annual_co2 = Decimal(str(details.get("calculated_annual_co2_for_this_input", "0"))).quantize(Decimal('0.1'))
            annual_multiplier = Decimal(str(details.get("annual_multiplier_used", "1")))
            annual_units = (Decimal(str(raw_value)) * annual_multiplier).quantize(Decimal('0.1') if '.' in str(raw_value) else Decimal('0'))

            formatted_text = formatted_text.replace(f"{{{{user_input_raw_{factor_id_str_placeholder}}}}}", escape(str(raw_value)))
            formatted_text = formatted_text.replace(f"{{{{user_input_unit_label_{factor_id_str_placeholder}}}}}", escape(str(unit_label)))
            formatted_text = formatted_text.replace(f"{{{{user_input_annual_co2_{factor_id_str_placeholder}}}}}", escape(str(annual_co2)))
            formatted_text = formatted_text.replace(f"{{{{user_input_annual_units_{factor_id_str_placeholder}}}}}", escape(str(annual_units)))

    # 3. Подстановка выбросов по категориям
    # Плейсхолдеры:
    # {{annual_emission_category_SLUG}} - годовые выбросы CO2 по категории с slug SLUG
    # {{annual_emission_category_name_SLUG}} - отображаемое имя категории с slug SLUG
    # {{category_percentage_SLUG}} - процент выбросов категории SLUG от общего следа
    
    # Сначала получим все ActivityCategory объекты, чтобы избежать многократных запросов в цикле
    all_categories_map = {cat.slug: cat.name for cat in ActivityCategory.objects.all()}

    for cat_slug_placeholder, emissions_val_decimal in category_breakdown_calc.items():
        emissions_val_quantized = emissions_val_decimal.quantize(Decimal('0.1'))
        cat_name_display = all_categories_map.get(cat_slug_placeholder, cat_slug_placeholder) # Имя категории

        formatted_text = formatted_text.replace(f"{{{{annual_emission_category_{cat_slug_placeholder}}}}}", escape(str(emissions_val_quantized)))
        formatted_text = formatted_text.replace(f"{{{{annual_emission_category_name_{cat_slug_placeholder}}}}}", escape(cat_name_display))
        
        if total_annual_emissions_calc > Decimal('0'):
            percentage_of_total = (emissions_val_decimal / total_annual_emissions_calc * Decimal('100')).quantize(Decimal('0.1'))
            formatted_text = formatted_text.replace(f"{{{{category_percentage_{cat_slug_placeholder}}}}}", escape(str(percentage_of_total)))
        else:
            formatted_text = formatted_text.replace(f"{{{{category_percentage_{cat_slug_placeholder}}}}}", "0")

    # 4. Подстановка общего годового выброса
    formatted_text = formatted_text.replace("{{total_annual_emissions_kg}}", escape(str(total_annual_emissions_calc)))
    
    # Очистка оставшихся нераспознанных плейсхолдеров (если есть)
    import re
    formatted_text = re.sub(r"\{\{.*?\}\}", "[нет данных]", formatted_text) # Заменяем на "[нет данных]" вместо удаления
    
    return formatted_text

def calculate_footprint_view(request):
    form = FootprintCalculatorForm(request.POST or None)
    results_data = None
    tips_by_category_display = {}
    calculation_error = None
    
    # Initialize these variables at the beginning of the function scope
    total_co2_emissions_kg_annual = Decimal('0.0')
    category_breakdown_kg_annual_calc = {}
    user_inputs_for_session_db = {}
    active_factors_map = {factor.id: factor for factor in EmissionFactor.objects.filter(is_active=True).select_related('activity_category')}


    if request.method == 'POST' and form.is_valid():
        try:
            # Reset for POST request before calculations
            total_co2_emissions_kg_annual = Decimal('0.0')
            category_breakdown_kg_annual_calc = {}
            user_inputs_for_session_db = {}
            # active_factors_map is already defined above, no need to redefine if it's static for the request

            # Запомним профиль
            selected_region = None
            profile_region_id = form.cleaned_data.get('profile_region')
            if profile_region_id:
                try:
                    selected_region = Region.objects.get(id=int(profile_region_id))
                except Exception:
                    selected_region = None
            # Fallback to default region if not explicitly selected
            if selected_region is None:
                try:
                    selected_region = Region.objects.filter(is_default=True).first()
                except Exception:
                    selected_region = None
            household_members = form.cleaned_data.get('profile_household_members')

            for field_name_form, value_form in form.cleaned_data.items():
                if field_name_form.startswith('factor_input_') and not field_name_form.endswith('_period') and value_form is not None:
                    try:
                        factor_id = int(field_name_form.split('_')[2])
                        factor_instance = active_factors_map.get(factor_id)
                        if not factor_instance:
                            logger.warning(f"Фактор с ID {factor_id} не найден среди активных при обработке формы.")
                            continue
                        current_value = Decimal(str(value_form))
                        annual_multiplier = Decimal('1.0')
                        period_field_name_form = f'{field_name_form}_period'
                        chosen_period_key = form.cleaned_data.get(period_field_name_form)
                        raw_input_unit_label = factor_instance.unit_name
                        if chosen_period_key and factor_instance.periodicity_options_for_form:
                            period_details = factor_instance.periodicity_options_for_form.get(chosen_period_key)
                            if period_details and 'annual_multiplier' in period_details:
                                annual_multiplier = Decimal(str(period_details['annual_multiplier']))
                                raw_input_unit_label = period_details.get('label', chosen_period_key)
                        
                        # Поддержка региональной интенсивности сети
                        co2_per_unit = factor_instance.co2_kg_per_unit
                        if getattr(factor_instance, 'use_region_grid_intensity', False) and selected_region:
                            co2_per_unit = selected_region.grid_intensity_kg_per_kwh

                        calculated_annual_co2_for_input = (current_value * annual_multiplier * co2_per_unit).quantize(Decimal('0.01'), ROUND_HALF_UP)
                        user_inputs_for_session_db[str(factor_id)] = {
                            "raw_value": float(current_value),
                            "input_unit_label": raw_input_unit_label,
                            "chosen_period_key_if_any": chosen_period_key,
                            "annual_multiplier_used": float(annual_multiplier),
                            "factor_co2_kg_per_unit": float(co2_per_unit),
                            "calculated_annual_co2_for_this_input": float(calculated_annual_co2_for_input)
                        }
                        emission_for_factor_annual = current_value * annual_multiplier * co2_per_unit
                        total_co2_emissions_kg_annual += emission_for_factor_annual
                        category_slug = factor_instance.activity_category.slug
                        category_breakdown_kg_annual_calc[category_slug] = \
                            category_breakdown_kg_annual_calc.get(category_slug, Decimal('0.0')) + emission_for_factor_annual
                    except (ValueError, TypeError) as e:
                        logger.error(f"Ошибка преобразования значения для поля {field_name_form}: {value_form}. Ошибка: {e}")
                        calculation_error = "Wystąpił błąd podczas przetwarzania wprowadzonych danych liczbowych. Proszę sprawdzić ich poprawność."
                        break
                    except Exception as e:
                        logger.error(f"Неожиданная ошибка при обработке фактора {factor_id} для поля {field_name_form}: {e}")
                        calculation_error = "Wystąpił błąd wewnętrzny podczas obliczeń. Proszę spróbować ponownie później."
                        break
            
            if not calculation_error:
                total_co2_emissions_kg_annual = total_co2_emissions_kg_annual.quantize(Decimal('0.01'), ROUND_HALF_UP)
                category_breakdown_kg_annual_for_db = {}
                category_breakdown_for_display = {}
                category_map = {cat.slug: cat.name for cat in ActivityCategory.objects.all()}
                for cat_slug, val_decimal in category_breakdown_kg_annual_calc.items():
                    val_quantized = val_decimal.quantize(Decimal('0.01'), ROUND_HALF_UP)
                    category_breakdown_kg_annual_for_db[cat_slug] = float(val_quantized)
                    if val_quantized > 0:
                         category_breakdown_for_display[category_map.get(cat_slug, cat_slug)] = val_quantized
                
                # Добавим профиль в inputs_data для истории
                if selected_region:
                    user_inputs_for_session_db["_profile_region"] = {
                        "id": selected_region.id,
                        "code": selected_region.code,
                        "name": selected_region.name,
                        "grid_intensity_kg_per_kwh": float(selected_region.grid_intensity_kg_per_kwh)
                    }
                if household_members:
                    user_inputs_for_session_db["_profile_household_members"] = int(household_members)

                session_record = UserFootprintSession.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    session_key=request.session.session_key if not request.user.is_authenticated else None,
                    inputs_data=user_inputs_for_session_db,
                    total_co2_emissions_kg_annual=total_co2_emissions_kg_annual,
                    category_breakdown_kg_annual=category_breakdown_kg_annual_for_db,
                    calculation_version="1.0"
                )

                average_footprint_value = None
                if hasattr(django_settings, 'AVERAGE_ANNUAL_CO2_FOOTPRINT_PL_KG'):
                    average_footprint_value = Decimal(str(django_settings.AVERAGE_ANNUAL_CO2_FOOTPRINT_PL_KG))
                difference_from_average = None
                abs_difference_from_average = None
                percentage_vs_average = None
                if average_footprint_value is not None and average_footprint_value > 0:
                    difference_from_average = total_co2_emissions_kg_annual - average_footprint_value
                    abs_difference_from_average = abs(difference_from_average)
                    if difference_from_average > 0:
                        percentage_vs_average = ((total_co2_emissions_kg_annual / average_footprint_value) * 100) - 100
                    elif difference_from_average < 0:
                        percentage_vs_average = 100 - ((total_co2_emissions_kg_annual / average_footprint_value) * 100)

                results_data = {
                    'total_co2_annual': total_co2_emissions_kg_annual,
                    'breakdown_annual_json': json.dumps({k: float(v) for k,v in category_breakdown_for_display.items()}),
                    'breakdown_annual_display': category_breakdown_for_display,
                    'session_id': session_record.id,
                    'average_footprint_pl': average_footprint_value,
                    'difference_from_average': difference_from_average,
                    'abs_difference_from_average': abs_difference_from_average,
                    'percentage_vs_average': percentage_vs_average,
                }

                all_active_tips = ReductionTip.objects.filter(is_active=True).prefetch_related(
                    'suggested_products', 'applies_to_categories'
                ).order_by('-priority', 'title')
                relevant_tips_ids_shown = set()
                for tip in all_active_tips:
                    show_this_tip = check_tip_conditions(
                        tip.trigger_conditions_json,
                        user_inputs_for_session_db,
                        category_breakdown_kg_annual_calc,
                        total_co2_emissions_kg_annual,
                        active_factors_map
                    )
                    if show_this_tip:
                        if tip.applies_to_categories.exists():
                            tip_applies_to_cat_with_emission = False
                            for cat_obj in tip.applies_to_categories.all():
                                if cat_obj.slug in category_breakdown_kg_annual_calc and category_breakdown_kg_annual_calc[cat_obj.slug] > 0:
                                    tip_applies_to_cat_with_emission = True
                                    break
                            if not tip_applies_to_cat_with_emission:
                                continue
                        
                        tip.calculated_potential_savings_kg = calculate_tip_savings(
                            tip_savings_logic_json=tip.estimated_co2_reduction_kg_annual_logic,
                            user_inputs_db=user_inputs_for_session_db,
                            category_breakdown_calc=category_breakdown_kg_annual_calc,
                            total_annual_emissions_calc=total_co2_emissions_kg_annual,
                            active_factors_map=active_factors_map
                        )
                        tip.formatted_description = format_tip_description(
                            tip.description_template,
                            user_inputs_for_session_db,
                            tip.calculated_potential_savings_kg,
                            category_breakdown_kg_annual_calc,
                            total_co2_emissions_kg_annual,
                            active_factors_map
                        )
                        if tip.id not in relevant_tips_ids_shown:
                            display_category_name = "Общие советы"
                            if tip.applies_to_categories.exists():
                                display_category_name = tip.applies_to_categories.first().name
                            if display_category_name not in tips_by_category_display:
                                tips_by_category_display[display_category_name] = []
                            tips_by_category_display[display_category_name].append(tip)
                            relevant_tips_ids_shown.add(tip.id)
                
                sorted_tips_by_category_display = {}
                # Ensure all_display_categories uses the correct source for slugs
                slugs_for_sorting = set()
                for cat_name_key in tips_by_category_display.keys():
                    if cat_name_key != "Общие советы":
                        # Find the slug for this category name
                        try:
                            cat_obj_sort = ActivityCategory.objects.get(name=cat_name_key)
                            slugs_for_sorting.add(cat_obj_sort.slug)
                        except ActivityCategory.DoesNotExist:
                            pass # Should not happen if keys are ActivityCategory.name
                
                all_display_categories = ActivityCategory.objects.filter(
                    slug__in=list(slugs_for_sorting)
                ).distinct().order_by('order')

                for activity_cat_sort in all_display_categories:
                    if activity_cat_sort.name in tips_by_category_display:
                         sorted_tips_by_category_display[activity_cat_sort.name] = tips_by_category_display[activity_cat_sort.name]
                if "Общие советы" in tips_by_category_display:
                    sorted_tips_by_category_display["Общие советы"] = tips_by_category_display["Общие советы"]
                tips_by_category_display = sorted_tips_by_category_display

        except Exception as e:
            logger.exception("Критическая ошибка при расчете углеродного следа.")
            calculation_error = f"Wystąpił nieoczekiwany błąd podczas obliczeń: {e}. Proszę spróbować ponownie później lub skontaktować się z pomocą techniczną."
    
    context = {
        'form': form,
        'results_data': results_data,
        'tips_by_category_display': {k: v for k, v in tips_by_category_display.items() if v},
        'calculation_error': calculation_error,
        'page_title': 'Eko-kalkulator śladu węglowego',
        'difference': results_data['difference_from_average'] if results_data and 'difference_from_average' in results_data else None,
    }
    return render(request, 'carbon_calculator/calculator_page.html', context)

@login_required
def user_footprint_history_view(request):
    history_sessions = UserFootprintSession.objects.filter(user=request.user).order_by('-calculated_at')
    # Prepare ascending-ordered points for chart: [{date: ISO8601, value: float}, ...]
    try:
        points = [
            {
                'date': hs.calculated_at.isoformat(),
                'value': float(hs.total_co2_emissions_kg_annual or 0),
            }
            for hs in history_sessions
        ]
        points.sort(key=lambda p: p['date'])
    except Exception:
        points = []

    context = {
        'history_sessions': history_sessions,
        'history_points': points,
        'page_title': 'Historia moich obliczeń śladu węglowego'
    }
    return render(request, 'carbon_calculator/footprint_history.html', context)

def methodology_view(request):
    context = {
        'page_title': 'Metodologia Eko-kalkulatora',
    }
    return render(request, 'carbon_calculator/methodology_page.html', context)