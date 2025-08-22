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
from django.utils.html import escape  # Bezpieczne wstawianie danych do tekstu

logger = logging.getLogger(__name__)

def check_tip_conditions(tip_conditions_json, user_inputs_db, category_breakdown_calc, total_annual_emissions_calc, active_factors_map):
    """
    Sprawdza, czy spełnione są warunki do wyświetlenia porady.
    :param tip_conditions_json: JSON trigger_conditions_json z ReductionTip
    :param user_inputs_db: Słownik user_inputs_for_session_db (dane wprowadzone przez użytkownika)
                           Struktura: { "factor_id_X": {"raw_value": Y, "chosen_period_key_if_any": Z, ...}, ...}
    :param category_breakdown_calc: Słownik category_breakdown_kg_annual_calc {category_slug: Decimal(value)}
    :param total_annual_emissions_calc: Decimal, całkowity roczny ślad
    :param active_factors_map: Słownik {factor_id: factor_instance} (dostęp do szczegółów czynników)
    :return: True, jeśli wszystkie warunki są spełnione (lub brak warunków), inaczej False
    """
    if not tip_conditions_json:
        return True  # Brak warunków oznacza poradę domyślnie stosowną

    if not isinstance(tip_conditions_json, list):
        logger.warning(f"trigger_conditions_json nie jest listą: {tip_conditions_json} dla porady.")
        return False  # Nieprawidłowy format warunków

    for condition in tip_conditions_json:
        if not isinstance(condition, dict):
            logger.warning(f"Element warunku nie jest słownikiem: {condition} dla porady.")
            return False  # Pomijamy niepoprawny warunek, uznając, że ogólnie warunek nie jest spełniony

        condition_type = condition.get("type")
        current_condition_met = False  # Flaga dla aktualnie sprawdzanego warunku

        try:
            if condition_type == "category_emission_gt":
                cat_slug = condition.get("category_slug")
                threshold = Decimal(str(condition.get("threshold_kg_annual", "0")))
                if cat_slug and cat_slug in category_breakdown_calc and category_breakdown_calc[cat_slug] > threshold:
                    current_condition_met = True

            elif condition_type == "category_emission_lt":
                cat_slug = condition.get("category_slug")
                threshold = Decimal(str(condition.get("threshold_kg_annual", "999999999")))  # Duża wartość domyślna
                # Jeśli kategorii nie ma w obliczeniu, jej emisje = 0, co jest mniejsze od progu
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
                    # Porównujemy surową wartość wprowadzoną przez użytkownika
                    raw_value = user_inputs_db[factor_id_str].get("raw_value")
                    if raw_value is not None and Decimal(str(raw_value)) > threshold_input_val:
                        current_condition_met = True

            elif condition_type == "input_value_equals":
                factor_id_str = str(condition.get("factor_id"))
                expected_val_str = str(condition.get("expected_value"))  # Oczekujemy string, bo opcje select to stringi
                if factor_id_str in user_inputs_db:
                    # Dla pól 'select' user_inputs_db[factor_id_str]["raw_value"] będzie łańcuchem (klucz opcji)
                    # Dla pól liczbowych to liczba, ale porównujemy jako tekst dla uniwersalności
                    raw_value = user_inputs_db[factor_id_str].get("raw_value")
                    if raw_value is not None and str(raw_value) == expected_val_str:
                        current_condition_met = True

            elif condition_type == "total_emission_gt":
                threshold_total = Decimal(str(condition.get("threshold_kg_annual", "0")))
                if total_annual_emissions_calc > threshold_total:
                    current_condition_met = True

            # Dodatkowe typy warunków można dodać później

            else:
                logger.warning(f"Nieznany lub niepełny typ warunku '{condition_type}' w: {condition} dla porady.")
                return False  # Nieznany warunek => ogólny warunek niespełniony

            if not current_condition_met:  # Jeśli któryś warunek z listy nie jest spełniony (logika AND)
                return False  # Przerywamy — nie wszystkie warunki są spełnione

        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Błąd przy przetwarzaniu warunku JSON {condition} dla porady: {e}")
            return False  # Uznajemy warunek za niespełniony przy błędzie

    return True  # Jeśli wszystkie warunki zostały spełnione

def calculate_tip_savings(tip_savings_logic_json, user_inputs_db, category_breakdown_calc, total_annual_emissions_calc, active_factors_map):
    """
    Oblicza potencjalną oszczędność CO2 dla porady.
    :param tip_savings_logic_json: JSON estimated_co2_reduction_kg_annual_logic
    :param user_inputs_db: Słownik user_inputs_for_session_db
                           Struktura: { "factor_id_X": {"raw_value": Y, "annual_multiplier_used": Z,
                                                       "calculated_annual_co2_for_this_input": C, ...}, ...}
    :param category_breakdown_calc: Słownik category_breakdown_kg_annual_calc {category_slug: Decimal(value)}
    :param total_annual_emissions_calc: Decimal, całkowity roczny ślad
    :param active_factors_map: Słownik {factor_id: factor_instance} (dostęp do co2_kg_per_unit)
    :return: Decimal (oszczędność w kg CO2/rok) lub None
    """
    if not tip_savings_logic_json or not isinstance(tip_savings_logic_json, dict):
        logger.debug(f"Brak logiki obliczania oszczędności lub nieprawidłowy format: {tip_savings_logic_json}")
        return None

    savings_type = tip_savings_logic_json.get("type")
    potential_savings = None
    quantizer = Decimal('0.1')  # Zaokrąglamy do 1 miejsca po przecinku

    try:
        if savings_type == "fixed":
            value_str = str(tip_savings_logic_json.get("value_kg_annual", "0"))
            potential_savings = Decimal(value_str)
            logger.debug(f"Obliczenie oszczędności (fixed): {potential_savings} kg/rok")

        elif savings_type == "percentage_of_category":
            cat_slug = tip_savings_logic_json.get("category_slug")
            percentage_str = str(tip_savings_logic_json.get("percentage", "0"))
            percentage = Decimal(percentage_str)

            if cat_slug in category_breakdown_calc and percentage > 0:
                category_emission = category_breakdown_calc[cat_slug]
                potential_savings = (category_emission * percentage / Decimal('100'))
                logger.debug(f"Oszczędność (percentage_of_category '{cat_slug}'): {category_emission} * {percentage}% = {potential_savings} kg/rok")
            else:
                logger.debug(f"Kategoria '{cat_slug}' nie znaleziona w emisjach lub procent = 0 dla percentage_of_category.")

        elif savings_type == "reduction_from_input":
            # Oszczędność = X% rocznych emisji związanych z konkretnym wejściem użytkownika
            input_factor_id_str = str(tip_savings_logic_json.get("input_factor_id"))
            reduction_percentage_str = str(tip_savings_logic_json.get("reduction_percentage", "0"))
            reduction_percentage = Decimal(reduction_percentage_str)

            if input_factor_id_str in user_inputs_db and reduction_percentage > 0:
                input_details = user_inputs_db[input_factor_id_str]
                # Używamy już obliczonych rocznych emisji dla tego wejścia
                annual_co2_for_this_input = Decimal(str(input_details.get("calculated_annual_co2_for_this_input", "0")))
                potential_savings = annual_co2_for_this_input * reduction_percentage / Decimal('100')
                logger.debug(f"Oszczędność (reduction_from_input factor_id={input_factor_id_str}): {annual_co2_for_this_input} * {reduction_percentage}% = {potential_savings} kg/rok")
            else:
                logger.debug(f"Czynnik ID {input_factor_id_str} nie znaleziony we wprowadzonych danych lub procent = 0 dla reduction_from_input.")

        elif savings_type == "activity_substitution":
            # Zastąpienie X% jednej aktywności (z oryginalnym CO2/jedn.) alternatywną (z nowym CO2/jedn.)
            orig_factor_id_str = str(tip_savings_logic_json.get("original_input_factor_id"))
            # CO2 na jednostkę alternatywnej aktywności
            alt_co2_per_unit_str = str(tip_savings_logic_json.get("alternative_co2_per_unit", "0"))
            alt_co2_per_unit = Decimal(alt_co2_per_unit_str)
            # Jaki procent oryginalnej aktywności jest zastępowany (domyślnie 100%)
            affected_input_percentage_str = str(tip_savings_logic_json.get("affected_input_percentage", "100"))
            affected_input_percentage = Decimal(affected_input_percentage_str)

            if orig_factor_id_str in user_inputs_db and affected_input_percentage > 0:
                original_input_details = user_inputs_db[orig_factor_id_str]
                original_factor_instance = active_factors_map.get(int(orig_factor_id_str))

                if original_factor_instance:
                    # Roczna liczba jednostek oryginalnej aktywności (np. roczny przebieg)
                    raw_value = Decimal(str(original_input_details.get("raw_value", "0")))
                    annual_multiplier = Decimal(str(original_input_details.get("annual_multiplier_used", "1")))
                    annual_units_of_activity = raw_value * annual_multiplier

                    # Jednostki aktywności, które podlegają zastąpieniu
                    units_to_substitute = annual_units_of_activity * (affected_input_percentage / Decimal('100'))

                    # Emisje oryginalnej aktywności dla zastępowanej części
                    original_emissions_from_substituted_part = units_to_substitute * original_factor_instance.co2_kg_per_unit

                    # Emisje z alternatywnej aktywności dla tej samej części
                    alternative_emissions_from_substituted_part = units_to_substitute * alt_co2_per_unit

                    potential_savings = original_emissions_from_substituted_part - alternative_emissions_from_substituted_part
                    logger.debug(f"Oszczędność (activity_substitution factor_id={orig_factor_id_str}): Savings={potential_savings} kg/rok")
                else:
                    logger.warning(f"Oryginalny czynnik ID {orig_factor_id_str} nie znaleziony w active_factors_map dla activity_substitution.")
            else:
                logger.debug(f"Czynnik ID {orig_factor_id_str} nie znaleziony we wprowadzonych danych lub procent = 0 dla activity_substitution.")

        elif savings_type == "direct_from_input_change":
            # Zakładamy, że porada sugeruje zmianę wartości konkretnego czynnika na nową
            input_factor_id_str = str(tip_savings_logic_json.get("input_factor_id"))
            new_value_for_input_str = str(tip_savings_logic_json.get("new_value_for_input", "0"))
            new_value_for_input = Decimal(new_value_for_input_str)

            # Okres dla nowej wartości (jeśli różni się od pierwotnej lub nie był podany)
            # Jeśli period_key_for_new_value nie podano, używamy annual_multiplier_used z oryginalnego wejścia
            new_period_key = tip_savings_logic_json.get("period_key_for_new_value")

            if input_factor_id_str in user_inputs_db:
                original_input_details = user_inputs_db[input_factor_id_str]
                factor_instance = active_factors_map.get(int(input_factor_id_str))

                if factor_instance:
                    # Oryginalne roczne emisje dla tego czynnika
                    original_annual_co2_for_input = Decimal(str(original_input_details.get("calculated_annual_co2_for_this_input", "0")))

                    # Obliczamy nowe roczne emisje
                    new_annual_multiplier = Decimal(str(original_input_details.get("annual_multiplier_used", "1")))  # Domyślnie
                    if new_period_key and getattr(factor_instance, 'periodicity_options_for_form', None):
                        period_details = factor_instance.periodicity_options_for_form.get(new_period_key)
                        if period_details and 'annual_multiplier' in period_details:
                            new_annual_multiplier = Decimal(str(period_details['annual_multiplier']))

                    new_annual_co2_for_input = (new_value_for_input * new_annual_multiplier * factor_instance.co2_kg_per_unit)

                    potential_savings = original_annual_co2_for_input - new_annual_co2_for_input
                    logger.debug(f"Oszczędność (direct_from_input_change factor_id={input_factor_id_str}): Original CO2={original_annual_co2_for_input}, New CO2={new_annual_co2_for_input}. Savings={potential_savings} kg/rok")
            else:
                logger.debug(f"Czynnik ID {input_factor_id_str} nie znaleziony we wprowadzonych danych dla direct_from_input_change.")

        else:
            logger.warning(f"Nieznany typ logiki oszczędności: '{savings_type}' dla porady.")

        if potential_savings is not None:
            # Oszczędność nie może być ujemna (porada nie powinna zwiększać śladu)
            return max(Decimal('0.0'), potential_savings.quantize(quantizer, ROUND_HALF_UP))

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Błąd typu/dostępu przy obliczaniu oszczędności (logika: {tip_savings_logic_json}): {e}")
    except Exception as e_global:
        logger.error(f"Nieoczekiwany błąd przy obliczaniu oszczędności porady (logika: {tip_savings_logic_json}): {e_global}")

    return None

def format_tip_description(description_template, user_inputs_db, tip_calculated_savings_kg,
                           category_breakdown_calc, total_annual_emissions_calc,
                           active_factors_map):
    """
    Formatuje szablon opisu porady, podstawiając wartości.
    """
    if not description_template:
        return ""

    formatted_text = str(description_template)  # Upewniamy się, że to string

    # 1. Podstawienie potencjalnej oszczędności
    if tip_calculated_savings_kg is not None:
        formatted_text = formatted_text.replace("{{potential_annual_savings_kg}}", escape(str(tip_calculated_savings_kg)))
    else:  # Jeśli oszczędność nie została obliczona
        formatted_text = formatted_text.replace("{{potential_annual_savings_kg}}", "brak oszacowania")

    # 2. Podstawienie wartości wejściowych użytkownika
    # Placeholdery:
    # {{user_input_raw_X}} - surowa wartość dla czynnika X
    # {{user_input_unit_label_X}} - jednostka dla surowej wartości czynnika X
    # {{user_input_annual_co2_X}} - roczne emisje CO2 od czynnika X
    # {{user_input_annual_units_X}} - roczna liczba jednostek dla czynnika X (surowa wartość * mnożnik roczny)
    # {{factor_name_X}} - nazwa czynnika X
    # {{factor_question_X}} - treść pytania dla czynnika X

    for factor_id_str_placeholder in list(user_inputs_db.keys()) + [str(f_id) for f_id in active_factors_map.keys()]:  # Pokryj też czynniki bez wejścia
        details = user_inputs_db.get(factor_id_str_placeholder)
        factor_instance = active_factors_map.get(int(factor_id_str_placeholder))

        if factor_instance:  # Nazwa i pytanie czynnika zawsze dostępne, jeśli istnieje
            formatted_text = formatted_text.replace(f"{{{{factor_name_{factor_id_str_placeholder}}}}}", escape(factor_instance.name))
            formatted_text = formatted_text.replace(f"{{{{factor_question_{factor_id_str_placeholder}}}}}", escape(factor_instance.form_question_text))

        if details:  # Jeśli było wejście dla tego czynnika
            raw_value = details.get("raw_value", "")
            unit_label = details.get("input_unit_label", "")
            annual_co2 = Decimal(str(details.get("calculated_annual_co2_for_this_input", "0"))).quantize(Decimal('0.1'))
            annual_multiplier = Decimal(str(details.get("annual_multiplier_used", "1")))
            annual_units = (Decimal(str(raw_value)) * annual_multiplier).quantize(Decimal('0.1') if '.' in str(raw_value) else Decimal('0'))

            formatted_text = formatted_text.replace(f"{{{{user_input_raw_{factor_id_str_placeholder}}}}}", escape(str(raw_value)))
            formatted_text = formatted_text.replace(f"{{{{user_input_unit_label_{factor_id_str_placeholder}}}}}", escape(str(unit_label)))
            formatted_text = formatted_text.replace(f"{{{{user_input_annual_co2_{factor_id_str_placeholder}}}}}", escape(str(annual_co2)))
            formatted_text = formatted_text.replace(f"{{{{user_input_annual_units_{factor_id_str_placeholder}}}}}", escape(str(annual_units)))

    # 3. Podstawienie emisji wg kategorii
    # Placeholdery:
    # {{annual_emission_category_SLUG}} - roczne emisje CO2 dla kategorii o slugu SLUG
    # {{annual_emission_category_name_SLUG}} - wyświetlana nazwa kategorii o slugu SLUG
    # {{category_percentage_SLUG}} - procent emisji kategorii SLUG względem całości

    # Najpierw pobierz wszystkie ActivityCategory, by uniknąć wielu zapytań w pętli
    all_categories_map = {cat.slug: cat.name for cat in ActivityCategory.objects.all()}

    for cat_slug_placeholder, emissions_val_decimal in category_breakdown_calc.items():
        emissions_val_quantized = emissions_val_decimal.quantize(Decimal('0.1'))
        cat_name_display = all_categories_map.get(cat_slug_placeholder, cat_slug_placeholder)  # Nazwa kategorii

        formatted_text = formatted_text.replace(f"{{{{annual_emission_category_{cat_slug_placeholder}}}}}", escape(str(emissions_val_quantized)))
        formatted_text = formatted_text.replace(f"{{{{annual_emission_category_name_{cat_slug_placeholder}}}}}", escape(cat_name_display))

        if total_annual_emissions_calc > Decimal('0'):
            percentage_of_total = (emissions_val_decimal / total_annual_emissions_calc * Decimal('100')).quantize(Decimal('0.1'))
            formatted_text = formatted_text.replace(f"{{{{category_percentage_{cat_slug_placeholder}}}}}", escape(str(percentage_of_total)))
        else:
            formatted_text = formatted_text.replace(f"{{{{category_percentage_{cat_slug_placeholder}}}}}", "0")

    # 4. Podstawienie łącznych rocznych emisji
    formatted_text = formatted_text.replace("{{total_annual_emissions_kg}}", escape(str(total_annual_emissions_calc)))

    # Czyszczenie pozostałych nierozpoznanych placeholderów (jeśli są)
    import re
    formatted_text = re.sub(r"\{\{.*?\}\}", "[brak danych]", formatted_text)  # Zastępujemy brakujące danymi

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

            # Zapamiętaj profil
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
                            logger.warning(f"Nie znaleziono aktywnego czynnika o ID {factor_id} podczas przetwarzania formularza.")
                            continue
                        # Variant A: for select fields, parse selected key as numeric value/multiplier
                        if getattr(factor_instance, 'form_field_type', 'number') == 'select':
                            try:
                                current_value = Decimal(str(value_form))
                            except Exception:
                                logger.warning(
                                    f"Czynnik typu select id={factor_id} ma nienumeryczny klucz opcji '{value_form}'. Pomijam ten czynnik w obliczeniach."
                                )
                                continue
                        else:
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
                        
                        # Obsługa regionalnej intensywności sieci
                        co2_per_unit = factor_instance.co2_kg_per_unit
                        if getattr(factor_instance, 'use_region_grid_intensity', False) and selected_region:
                            co2_per_unit = selected_region.grid_intensity_kg_per_kwh

                        # Apply household division if factor is per_household and household_members provided
                        household_divisor = Decimal('1')
                        if getattr(factor_instance, 'per_household', False) and household_members:
                            try:
                                hm = Decimal(str(household_members))
                                if hm > 0:
                                    household_divisor = hm
                            except Exception:
                                pass

                        calculated_annual_co2_for_input = (
                            (current_value * annual_multiplier * co2_per_unit) / household_divisor
                        ).quantize(Decimal('0.01'), ROUND_HALF_UP)
                        user_inputs_for_session_db[str(factor_id)] = {
                            "raw_value": float(current_value),
                            "input_unit_label": raw_input_unit_label,
                            "chosen_period_key_if_any": chosen_period_key,
                            "annual_multiplier_used": float(annual_multiplier),
                            "factor_co2_kg_per_unit": float(co2_per_unit),
                            "calculated_annual_co2_for_this_input": float(calculated_annual_co2_for_input)
                        }
                        emission_for_factor_annual = (current_value * annual_multiplier * co2_per_unit) / household_divisor
                        total_co2_emissions_kg_annual += emission_for_factor_annual
                        category_slug = factor_instance.activity_category.slug
                        category_breakdown_kg_annual_calc[category_slug] = \
                            category_breakdown_kg_annual_calc.get(category_slug, Decimal('0.0')) + emission_for_factor_annual
                    except (ValueError, TypeError) as e:
                        logger.error(f"Błąd konwersji wartości dla pola {field_name_form}: {value_form}. Błąd: {e}")
                        calculation_error = "Wystąpił błąd podczas przetwarzania wprowadzonych danych liczbowych. Proszę sprawdzić ich poprawność."
                        break
                    except Exception as e:
                        logger.error(f"Nieoczekiwany błąd podczas przetwarzania czynnika {factor_id} dla pola {field_name_form}: {e}")
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
                
                # Dodaj profil do inputs_data dla historii
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
                            display_category_name = "Wskazówki ogólne"
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
                    if cat_name_key != "Wskazówki ogólne":
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
                if "Wskazówki ogólne" in tips_by_category_display:
                    sorted_tips_by_category_display["Wskazówki ogólne"] = tips_by_category_display["Wskazówki ogólne"]
                tips_by_category_display = sorted_tips_by_category_display

        except Exception as e:
            logger.exception("Krytyczny błąd podczas obliczania śladu węglowego.")
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
    'history_points_json': json.dumps(points),
        'page_title': 'Historia moich obliczeń śladu węglowego'
    }
    return render(request, 'carbon_calculator/footprint_history.html', context)

def methodology_view(request):
    context = {
        'page_title': 'Metodologia Eko-kalkulatora',
    }
    return render(request, 'carbon_calculator/methodology_page.html', context)