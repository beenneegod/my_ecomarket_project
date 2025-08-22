# carbon_calculator/templatetags/calculator_tags.py
from django import template
from carbon_calculator.views import Decimal
register = template.Library()

@register.filter(name='get_form_field')
def get_form_field(form, field_name_str):
    """
    Pozwala pobrać pole formularza po jego nazwie (łańcuch znaków).
    Użycie: {{ my_form|get_form_field:dynamic_field_name_variable }}
    """
    try:
        return form[field_name_str]
    except KeyError:
        return None

@register.simple_tag
def get_bound_field(form, field_name_str):
    """
    Zwraca powiązane pole (BoundField) formularza według nazwy.
    Użycie: {% get_bound_field my_form dynamic_field_name_variable as my_field %}
        {{ my_field.label_tag }} {{ my_field }} ...
    """
    try:
        return form[field_name_str]
    except KeyError:
        return None
    

@register.filter
def multiply(value, arg):
    try: return Decimal(str(value)) * Decimal(str(arg))
    except: return ''

@register.filter
def subtract(value, arg):
    try: return Decimal(str(value)) - Decimal(str(arg))
    except: return ''

@register.filter
def divide(value, arg):
    try:
        val_dec = Decimal(str(value))
        arg_dec = Decimal(str(arg))
        return val_dec / arg_dec if arg_dec != 0 else None
    except: return ''