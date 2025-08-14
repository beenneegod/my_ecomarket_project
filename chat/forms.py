from django import forms
from .models import ChatRoom, Message


class ChatRoomForm(forms.ModelForm):
    class Meta:
        model = ChatRoom
        fields = ['name', 'topic', 'is_private']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nazwa pokoju'}),
            'topic': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Temat (opcjonalnie)'}),
            'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Napisz wiadomość…'}),
        }
