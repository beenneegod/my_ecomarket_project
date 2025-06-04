from django.test import TestCase
from carbon_calculator.models import EmissionFactor, ActivityCategory
from django.core.exceptions import ValidationError
from decimal import Decimal

class EmissionFactorValidationTest(TestCase):
    def setUp(self):
        self.category = ActivityCategory.objects.create(name="Transport")

    def test_form_field_options_valid(self):
        factor = EmissionFactor(
            activity_category=self.category,
            name="Car",
            unit_name="km",
            co2_kg_per_unit=Decimal('0.2'),
            form_field_type='select',
            form_field_options={"eco": "Eco mode", "sport": "Sport mode"},
            form_question_text="How many km?"
        )
        # Should not raise
        factor.full_clean()

    def test_form_field_options_invalid_type(self):
        factor = EmissionFactor(
            activity_category=self.category,
            name="Car",
            unit_name="km",
            co2_kg_per_unit=Decimal('0.2'),
            form_field_type='select',
            form_field_options=["eco", "sport"], # Not a dict
            form_question_text="How many km?"
        )
        with self.assertRaises(ValidationError):
            factor.full_clean()

    def test_form_field_options_invalid_key(self):
        factor = EmissionFactor(
            activity_category=self.category,
            name="Car",
            unit_name="km",
            co2_kg_per_unit=Decimal('0.2'),
            form_field_type='select',
            form_field_options={1: "Eco mode"}, # Key is not a string
            form_question_text="How many km?"
        )
        with self.assertRaises(ValidationError):
            factor.full_clean()

    def test_form_field_options_invalid_value(self):
        factor = EmissionFactor(
            activity_category=self.category,
            name="Car",
            unit_name="km",
            co2_kg_per_unit=Decimal('0.2'),
            form_field_type='select',
            form_field_options={"eco": [1,2,3]}, # Value is not str/int/float
            form_question_text="How many km?"
        )
        with self.assertRaises(ValidationError):
            factor.full_clean()
