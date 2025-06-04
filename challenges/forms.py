# challenges/forms.py
from django import forms
from .models import UserChallengeParticipation

class ChallengeParticipationForm(forms.ModelForm): # Форма для отметки о выполнении с комментарием
    class Meta:
        model = UserChallengeParticipation
        fields = ['user_notes'] # Например, только заметки
        widgets = {
            'user_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Twój raport lub komentarz do wykonania (opcjonalnie)'}),
        }
        labels = {
            'user_notes': 'Komentarz do wykonania',
        }