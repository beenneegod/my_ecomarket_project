# challenges/forms.py
from django import forms
from .models import UserChallengeParticipation

class ChallengeParticipationForm(forms.ModelForm): # Форма для отметки о выполнении с комментарием и доказательством
    class Meta:
        model = UserChallengeParticipation
        fields = ['user_notes', 'proof_file']
        widgets = {
            'user_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Twój raport lub komentarz do wykonania (min. 10 znaków)'}),
        }
        labels = {
            'user_notes': 'Komentarz do wykonania',
            'proof_file': 'Dowód (zdjęcie/wideo)',
        }

    def clean(self):
        cleaned = super().clean()
        notes = cleaned.get('user_notes')
        proof = cleaned.get('proof_file')
        # Требуем хотя бы одно, но лучше оба; сделаем оба обязательными по требованиям пользователя
        if not notes or len(notes.strip()) < 10:
            self.add_error('user_notes', 'Opisz krótko wykonanie (min. 10 znaków).')
        if not proof:
            self.add_error('proof_file', 'Załącz zdjęcie lub wideo jako dowód.')
        else:
            # 10 MB limit
            max_size = 10 * 1024 * 1024
            try:
                size = getattr(proof, 'size', None)
            except Exception:
                size = None
            if size is not None and size > max_size:
                self.add_error('proof_file', 'Maksymalny rozmiar pliku to 10 MB.')
        return cleaned