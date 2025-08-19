from django import forms
from .models import EcoPlace, PlaceReview


class EcoPlaceForm(forms.ModelForm):
    class Meta:
        model = EcoPlace
        fields = [
            "name",
            "category",
            "city",
            "address",
            "lat",
            "lng",
            "description",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Np.: Sklep zero‑waste",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Miasto",
                }
            ),
            "address": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ulica, numer domu (opcjonalnie)",
                }
            ),
            "lat": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "any",
                    "placeholder": "Np. 52.2298",
                    "min": "-90",
                    "max": "90",
                }
            ),
            "lng": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "any",
                    "placeholder": "Np. 21.0118",
                    "min": "-180",
                    "max": "180",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                    "placeholder": "Krótki opis (opcjonalnie)",
                }
            ),
        }


class PlaceReviewForm(forms.ModelForm):
    class Meta:
        model = PlaceReview
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 5}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Opcjonalny komentarz"}),
        }
