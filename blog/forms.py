# blog/forms.py
from django import forms
from .models import Comment

class CommentForm(forms.ModelForm):
    MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB
    ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif']
    class Meta:
        model = Comment
        fields = ('body', 'image') # Добавляем поле 'image'
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3, # Можно сделать чуть меньше строк по умолчанию
                'placeholder': 'Napisz swój komentarz...'
            }),
            'image': forms.ClearableFileInput(attrs={ # Виджет для загрузки файла (скрытый, используем кастомную кнопку)
                'class': 'form-control d-none js-comment-image-input',
                'accept': 'image/*'
            }),
        }
        labels = {
            'body': '', # Убираем метку для основного текста, если placeholder достаточен
            'image': 'Dodaj obrazek (opcjonalnie):'
        }
        help_texts = {
            'image': 'Maksymalny rozmiar pliku: 2MB. Dozwolone formaty: JPG, PNG, GIF.', # Пример текста помощи
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image: # Проверяем, только если файл был загружен
            if image.size > self.MAX_IMAGE_SIZE:
                raise forms.ValidationError(f"Rozmiar pliku obrazka nie może przekraczać {self.MAX_IMAGE_SIZE // 1024 // 1024} MB.")
            if image.content_type not in self.ALLOWED_IMAGE_TYPES:
                raise forms.ValidationError("Niedozwolony typ pliku. Proszę załadować obrazek w formacie JPG, PNG lub GIF.")
        return image