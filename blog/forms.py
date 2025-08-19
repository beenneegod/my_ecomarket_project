# blog/forms.py
from django import forms
from .models import Comment
import random
import uuid

class CommentForm(forms.ModelForm):
    MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB
    ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif']

    # Simple math captcha
    captcha = forms.CharField(required=True)
    captcha_key = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Comment
        fields = ('body', 'image')  # captcha fields are non-model form fields
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Napisz swój komentarz...'
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control d-none js-comment-image-input',
                'accept': 'image/*'
            }),
        }
        labels = {
            'body': '',
            'image': 'Dodaj obrazek (opcjonalnie):'
        }
        help_texts = {
            'image': 'Maksymalny rozmiar pliku: 2MB. Dozwolone formaty: JPG, PNG, GIF.'
        }

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        # Configure captcha label and key
        if request is not None:
            if not self.is_bound:
                # Generate task
                a = random.randint(1, 9)
                b = random.randint(1, 9)
                key = f"cmt:{uuid.uuid4().hex}"
                request.session[key] = a + b
                self.fields['captcha_key'].initial = key
                self.fields['captcha'].label = f"Ile to jest {a} + {b}?"
                self.fields['captcha'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Wpisz wynik'})
            else:
                # Preserve label if possible (not strictly needed for server validation)
                self.fields['captcha'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Wpisz wynik'})

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.size > self.MAX_IMAGE_SIZE:
                raise forms.ValidationError(f"Rozmiar pliku obrazka nie może przekraczać {self.MAX_IMAGE_SIZE // 1024 // 1024} MB.")
            if image.content_type not in self.ALLOWED_IMAGE_TYPES:
                raise forms.ValidationError("Niedozwolony typ pliku. Proszę załadować obrazek w formacie JPG, PNG lub GIF.")
        return image

    def clean_captcha(self):
        value = (self.cleaned_data.get('captcha') or '').strip()
        key = (self.data.get('captcha_key') or self.cleaned_data.get('captcha_key') or '').strip()
        if not key or self.request is None:
            raise forms.ValidationError("Błąd walidacji CAPTCHA. Odśwież stronę i spróbuj ponownie.")
        try:
            expected = int(self.request.session.get(key))
        except Exception:
            expected = None
        # Clean up the key regardless of result
        try:
            if key in self.request.session:
                del self.request.session[key]
        except Exception:
            pass
        try:
            got = int(value)
        except Exception:
            raise forms.ValidationError("Wpisz liczbę — wynik działania.")
        if expected is None or got != expected:
            raise forms.ValidationError("Nieprawidłowy wynik zadania.")
        return value