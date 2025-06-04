# carbon_calculator/views.py
from django.shortcuts import render
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from .forms import FootprintCalculatorForm
from .models import EmissionFactor, UserFootprintSession, ReductionTip, ActivityCategory
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
import random # Make sure random is imported
from django.conf import settings as django_settings # For accessing AVERAGE_ANNUAL_CO2_FOOTPRINT_PL_KG
from django.utils.html import escape

logger = logging.getLogger(__name__)

def check_tip_conditions(tip_conditions_json, user_inputs_db, category_breakdown_calc, total_annual_emissions_calc):
    if not tip_conditions_json:
        return True
    if not isinstance(tip_conditions_json, list):
        logger.warning(f"trigger_conditions_json не является списком: {tip_conditions_json}")
        return False
    all_conditions_met = True
    for condition in tip_conditions_json:
        if not isinstance(condition, dict):
            logger.warning(f"Элемент условия не является словарем: {condition}")
            all_conditions_met = False; break
        condition_type = condition.get("type")
        current_condition_met = False
        try:
            if condition_type == "category_emission_gt":
                cat_slug = condition.get("category_slug")
                threshold = Decimal(str(condition.get("threshold_kg_annual", "0")))
                if cat_slug and cat_slug in category_breakdown_calc and category_breakdown_calc[cat_slug] > threshold:
                    current_condition_met = True
            elif condition_type == "category_emission_lt":
                cat_slug = condition.get("category_slug")
                threshold = Decimal(str(condition.get("threshold_kg_annual", "999999")))
                if cat_slug and cat_slug in category_breakdown_calc and category_breakdown_calc[cat_slug] < threshold:
                    current_condition_met = True
                elif cat_slug and cat_slug not in category_breakdown_calc:
                     current_condition_met = True
            elif condition_type == "category_emission_percentage_gt":
                cat_slug = condition.get("category_slug")
                threshold_percentage = Decimal(str(condition.get("percentage", "0")))
                if total_annual_emissions_calc > 0 and cat_slug and cat_slug in category_breakdown_calc:
                    category_percentage = (category_breakdown_calc[cat_slug] / total_annual_emissions_calc) * 100
                    if category_percentage > threshold_percentage:
                        current_condition_met = True
            elif condition_type == "input_value_gt":
                factor_id_str = str(condition.get("factor_id"))
                threshold_input_val = Decimal(str(condition.get("threshold_value", "0")))
                if factor_id_str in user_inputs_db and \
                   Decimal(str(user_inputs_db[factor_id_str].get("raw_value", "0"))) > threshold_input_val:
                    current_condition_met = True
            else:
                logger.warning(f"Неизвестный тип условия '{condition_type}' или неполные данные в условии: {condition}")
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Ошибка при обработке условия {condition}: {e}")
            all_conditions_met = False; break
        if not current_condition_met:
            all_conditions_met = False
            break
    return all_conditions_met

def calculate_tip_savings(tip_savings_logic_json, user_inputs_db, category_breakdown_calc, total_annual_emissions_calc, active_factors_map):
    if not tip_savings_logic_json or not isinstance(tip_savings_logic_json, dict):
        return None
    savings_type = tip_savings_logic_json.get("type")
    potential_savings = None
    try:
        if savings_type == "fixed":
            potential_savings = Decimal(str(tip_savings_logic_json.get("value_kg_annual", "0")))
        elif savings_type == "percentage_of_category":
            cat_slug = tip_savings_logic_json.get("category_slug")
            percentage = Decimal(str(tip_savings_logic_json.get("percentage", "0")))
            if cat_slug in category_breakdown_calc and percentage > 0:
                potential_savings = (category_breakdown_calc[cat_slug] * percentage / Decimal('100'))
        elif savings_type == "reduction_from_input":
            input_factor_id_str = str(tip_savings_logic_json.get("input_factor_id"))
            reduction_percentage = Decimal(str(tip_savings_logic_json.get("reduction_percentage", "0")))
            if input_factor_id_str in user_inputs_db and reduction_percentage > 0:
                annual_co2_for_this_input = Decimal(str(user_inputs_db[input_factor_id_str].get("calculated_annual_co2_for_this_input", "0")))
                potential_savings = annual_co2_for_this_input * reduction_percentage / Decimal('100')
        elif savings_type == "activity_substitution":
            orig_factor_id_str = str(tip_savings_logic_json.get("original_input_factor_id"))
            alt_co2_per_unit = Decimal(str(tip_savings_logic_json.get("alternative_co2_per_unit", "0")))
            affected_percentage = Decimal(str(tip_savings_logic_json.get("affected_input_percentage", "100")))
            if orig_factor_id_str in user_inputs_db:
                original_input_details = user_inputs_db[orig_factor_id_str]
                original_factor_instance = active_factors_map.get(int(orig_factor_id_str))
                if original_factor_instance:
                    annual_units_of_activity = Decimal(str(original_input_details.get("raw_value", "0"))) * \
                                               Decimal(str(original_input_details.get("annual_multiplier_used", "1")))
                    original_emissions_affected_part = (annual_units_of_activity * (affected_percentage / Decimal('100'))) * \
                                                       original_factor_instance.co2_kg_per_unit
                    alternative_emissions_affected_part = (annual_units_of_activity * (affected_percentage / Decimal('100'))) * \
                                                          alt_co2_per_unit
                    potential_savings = original_emissions_affected_part - alternative_emissions_affected_part
        if potential_savings is not None:
            return potential_savings.quantize(Decimal('0.1'), ROUND_HALF_UP)
    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Ошибка при расчете экономии для совета (логика: {tip_savings_logic_json}): {e}")
    return None

def format_tip_description(description_template, user_inputs_db, tip_calculated_savings_kg, category_breakdown_calc, total_annual_emissions_calc):
    formatted_text = description_template
    if tip_calculated_savings_kg is not None:
        formatted_text = formatted_text.replace("{{potential_annual_savings_kg}}", escape(str(tip_calculated_savings_kg)))
    for factor_id_str, details in user_inputs_db.items():
        raw_value_placeholder = f"{{{{user_input_raw_{factor_id_str}}}}}" 
        if raw_value_placeholder in formatted_text:
            formatted_text = formatted_text.replace(raw_value_placeholder, escape(str(details.get("raw_value", ""))))
        unit_label_placeholder = f"{{{{user_input_unit_label_{factor_id_str}}}}}"
        if unit_label_placeholder in formatted_text:
            formatted_text = formatted_text.replace(unit_label_placeholder, escape(str(details.get("input_unit_label", ""))))
        annual_co2_placeholder = f"{{{{user_input_annual_co2_{factor_id_str}}}}}"
        if annual_co2_placeholder in formatted_text:
             formatted_text = formatted_text.replace(annual_co2_placeholder, escape(str(Decimal(str(details.get("calculated_annual_co2_for_this_input","0"))).quantize(Decimal('0.1')) )))
    for cat_slug, emissions_val in category_breakdown_calc.items():
        try:
            # Ensure ActivityCategory is imported if not already: from .models import ActivityCategory
            cat_name = ActivityCategory.objects.get(slug=cat_slug).name
            formatted_text = formatted_text.replace(f"{{{{annual_emission_category_{cat_slug}}}}}", escape(str(emissions_val.quantize(Decimal('0.1')))))
            formatted_text = formatted_text.replace(f"{{{{annual_emission_category_name_{cat_slug}}}}}", escape(cat_name))
        except ActivityCategory.DoesNotExist:
            pass
    formatted_text = formatted_text.replace("{{total_annual_emissions_kg}}", escape(str(total_annual_emissions_calc)))
    import re
    formatted_text = re.sub(r"\{\{.*?\}\}", "", formatted_text) # Clean up unused placeholders
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
                        
                        calculated_annual_co2_for_input = (current_value * annual_multiplier * factor_instance.co2_kg_per_unit).quantize(Decimal('0.01'), ROUND_HALF_UP)
                        user_inputs_for_session_db[str(factor_id)] = {
                            "raw_value": float(current_value),
                            "input_unit_label": raw_input_unit_label,
                            "chosen_period_key_if_any": chosen_period_key,
                            "annual_multiplier_used": float(annual_multiplier),
                            "factor_co2_kg_per_unit": float(factor_instance.co2_kg_per_unit),
                            "calculated_annual_co2_for_this_input": float(calculated_annual_co2_for_input)
                        }
                        emission_for_factor_annual = current_value * annual_multiplier * factor_instance.co2_kg_per_unit
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
                        calculation_error = "Wystąpił błąд wewnętrzny podczas obliczeń. Proszę spróbować ponownie później."
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
                    show_this_tip = check_tip_conditions( # Renamed show_tip to show_this_tip
                        tip.trigger_conditions_json,
                        user_inputs_for_session_db,
                        category_breakdown_kg_annual_calc,
                        total_co2_emissions_kg_annual
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
                            tip.estimated_co2_reduction_kg_annual_logic,
                            user_inputs_for_session_db,
                            category_breakdown_kg_annual_calc,
                            total_co2_emissions_kg_annual,
                            active_factors_map
                        )
                        tip.formatted_description = format_tip_description(
                            tip.description_template,
                            user_inputs_for_session_db,
                            tip.calculated_potential_savings_kg,
                            category_breakdown_kg_annual_calc,
                            total_co2_emissions_kg_annual
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
    context = {
        'history_sessions': history_sessions,
        'page_title': 'Historia moich obliczeń śladu węglowego'
    }
    return render(request, 'carbon_calculator/footprint_history.html', context)

def methodology_view(request):
    context = {
        'page_title': 'Metodologia Eko-kalkulatora',
    }
    return render(request, 'carbon_calculator/methodology_page.html', context)