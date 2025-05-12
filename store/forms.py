# store/forms.py

from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm     
)
from django.contrib.auth.models import User # Если нужна стандартная модель User
from .models import Order

class OrderCreateForm(forms.ModelForm):
    class Meta:
        model = Order
        # Указываем поля модели Order, которые пользователь должен заполнить
        fields = [
            'first_name', 'last_name', 'email', 'address_line_1',
            'address_line_2', 'postal_code', 'city', 'country'
        ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Добавляем Bootstrap классы и атрибуты required к полям
        self.fields['first_name'].widget.attrs.update(
            {'class': 'form-control', 'required': 'required'}
        )
        self.fields['last_name'].widget.attrs.update(
            {'class': 'form-control', 'required': 'required'}
        )
        self.fields['email'].widget.attrs.update(
            {'class': 'form-control', 'placeholder': 'you@example.com', 'required': 'required'}
        )
        self.fields['address_line_1'].widget.attrs.update(
            {'class': 'form-control', 'placeholder': 'Ulica, numer domu, mieszkania', 'required': 'required'}
        )
        self.fields['address_line_2'].widget.attrs.update(
            {'class': 'form-control'} # Это поле не обязательное
        )
        self.fields['postal_code'].widget.attrs.update(
            {'class': 'form-control', 'required': 'required'}
        )
        self.fields['city'].widget.attrs.update(
            {'class': 'form-control', 'required': 'required'}
        )
        self.fields['country'].widget.attrs.update(
            {'class': 'form-control', 'required': 'required'}
        )
# Можно использовать стандартную форму или расширить ее, если нужны доп. поля
class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'you@example.com'}) # <--- ДОБАВЛЯЕМ КЛАССЫ
    )
    first_name = forms.CharField(
        required=False, # Стандартно не обязательное
        widget=forms.TextInput(attrs={'class': 'form-control form-control-lg'})
    )
    last_name = forms.CharField(
        required=False, # Стандартно не обязательное
        widget=forms.TextInput(attrs={'class': 'form-control form-control-lg'}) 
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        # Пароль обрабатывается базовым классом UserCreationForm


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update(
            {'class': 'form-control form-control-lg', 'placeholder': 'Nazwa użytkownika', 'autofocus': 'autofocus'}
        )
        self.fields['password1'].widget.attrs.update(
            {'class': 'form-control form-control-lg', 'placeholder': 'Hasło'}
        )
        self.fields['password2'].widget.attrs.update(
            {'class': 'form-control form-control-lg', 'placeholder': 'Potwierdź hasło'}
        )

class CustomAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update(
            {'class': 'form-control form-control-lg', 'placeholder': 'Nazwa użytkownika', 'autofocus': 'autofocus'}
        )
        self.fields['password'].widget.attrs.update(
            {'class': 'form-control form-control-lg', 'placeholder': 'Hasło'}
        )

class CustomPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update(
            {'class': 'form-control form-control-lg', 'placeholder': 'Adres email', 'type': 'email'}
        )

class CustomSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].widget.attrs.update(
            {'class': 'form-control form-control-lg', 'placeholder': 'Nowe hasło'}
        )
        self.fields['new_password2'].widget.attrs.update(
            {'class': 'form-control form-control-lg', 'placeholder': 'Potwierdź nowe hasło'}
        )
    # Можно добавить кастомную валидацию, если нужно
    # def clean_email(self):
    #     email = self.cleaned_data['email']
    #     if User.objects.filter(email=email).exists():
    #         raise forms.ValidationError("Пользователь с таким email уже существует.")
    #     return email