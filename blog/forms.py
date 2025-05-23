# blog/forms.py
from django import forms
from .models import Comment

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ('body', 'image') # Добавляем поле 'image'
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3, # Можно сделать чуть меньше строк по умолчанию
                'placeholder': 'Napisz swój komentarz...'
            }),
            'image': forms.ClearableFileInput(attrs={ # Виджет для загрузки файла
                'class': 'form-control mt-2' # Добавим отступ сверху
            }),
        }
        labels = {
            'body': '', # Убираем метку для основного текста, если placeholder достаточен
            'image': 'Dodaj obrazek (opcjonalnie):'
        }
        help_texts = {
            'image': 'Maksymalny rozmiar pliku: 2MB. Dozwolone formaty: JPG, PNG, GIF.', # Пример текста помощи
        }