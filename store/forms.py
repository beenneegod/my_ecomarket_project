# store/forms.py

from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm     
)
from django.contrib.auth.models import User # Если нужна стандартная модель User
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone # Импортируем timezone
from .models import Order
from .models import Profile, SubscriptionBoxType, Coupon, UserCoupon # Добавляем Coupon и UserCoupon


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

class ProfileUpdateForm(forms.ModelForm):
    MAX_AVATAR_SIZE = 2 * 1024 * 1024 # 2 MB
    ALLOWED_AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/gif']
    class Meta:
        model = Profile
        fields = ['avatar', 'bio'] # Поля, которые пользователь сможет редактировать
        widgets = {
            # Hide native file input; label[for] triggers it
            'avatar': forms.ClearableFileInput(attrs={'class': 'js-avatar-input', 'accept': 'image/*', 'style': 'display:none'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Napisz coś o sobie...'}),
        }
        labels = {
            'avatar': 'Zmień awatar',
            'bio': 'O Tobie',
        }

    def clean_avatar(self):
        # Если пользователь нажал 'Usuń zdjęcie' — пропускаем любые проверки, аватар будет очищен в save()
        if self.data.get('avatar_clear') in ('1', 'true', 'on'):
            return None

        avatar = self.cleaned_data.get('avatar')
        # Валидируем ТОЛЬКО если пришёл новый загруженный файл
        if 'avatar' in self.files:
            uploaded = self.files.get('avatar')
            if isinstance(uploaded, UploadedFile):
                if uploaded.size and uploaded.size > self.MAX_AVATAR_SIZE:
                    raise forms.ValidationError(
                        f"Rozmiar pliku awatara nie może przekraczać {self.MAX_AVATAR_SIZE // 1024 // 1024} MB."
                    )
                content_type = getattr(uploaded, 'content_type', '') or ''
                if content_type not in self.ALLOWED_AVATAR_TYPES:
                    raise forms.ValidationError("Niedozwolony typ pliku. Proszę wgrać JPEG, PNG lub GIF.")
        # Если файла нет в self.files (не загружали новый) — ничего не проверяем
        return avatar

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Если пользователь нажал "Usuń zdjęcie" — удаляем файл и очищаем поле
        if self.data.get('avatar_clear') in ('1', 'true', 'on'):
            try:
                if instance.avatar:
                    storage = instance.avatar.storage
                    name = instance.avatar.name
                    instance.avatar.delete(save=False)
                    if storage and name:
                        try:
                            storage.delete(name)
                        except Exception:
                            pass
                instance.avatar = None
            except Exception:
                instance.avatar = None
        else:
            # Дедупликация: если загружен новый файл и он совпадает с текущим по хешу — не пересохраняем
            uploaded = self.files.get('avatar') if hasattr(self, 'files') else None
            try:
                if uploaded and instance.pk and getattr(instance, 'avatar'):
                    # Вычисляем SHA256 загруженного файла
                    import hashlib
                    hasher_new = hashlib.sha256()
                    for chunk in uploaded.chunks():
                        hasher_new.update(chunk)
                    new_digest = hasher_new.hexdigest()

                    # Вычисляем SHA256 текущего файла из стораджа
                    current_file = instance.avatar
                    hasher_old = hashlib.sha256()
                    try:
                        with current_file.open('rb') as f:
                            for chunk in iter(lambda: f.read(8192), b''):
                                hasher_old.update(chunk)
                        old_digest = hasher_old.hexdigest()
                    except Exception:
                        old_digest = None

                    if old_digest and new_digest == old_digest:
                        # Совпадает: вернуть предыдущее значение и отбросить новое
                        # Сбрасываем поле к исходному, чтобы Django не сохранил новое
                        self.cleaned_data['avatar'] = current_file
                        instance.avatar = current_file
                        # Также очистим self.files, чтобы не триггерить перезапись
                        try:
                            self.files.pop('avatar', None)
                        except Exception:
                            pass
            except Exception:
                # На ошибке дедупликации просто продолжаем обычный путь
                pass
        if commit:
            instance.save()
        return instance

class SubscriptionChoiceForm(forms.Form):
    # Поле для выбора типа подписочного бокса.
    # ModelChoiceField позволяет выбрать из существующих объектов модели.
    box_type = forms.ModelChoiceField(
        queryset=SubscriptionBoxType.objects.filter(is_active=True), # Показываем только активные боксы
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}), # Отображаем как радиокнопки
        empty_label=None, # Убираем пустой вариант "-- Válassz --"
        label="Wybierz rodzaj Eko Boxa"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Можно добавить кастомные стили или логику сюда, если нужно
        # Например, если хочешь, чтобы радиокнопки отображались в несколько колонок или иначе.
        # Но Bootstrap 5 хорошо стилизует .form-check-input для RadioSelect.
        self.fields['box_type'].label_attrs = {'class': 'h5 mb-3 d-block'} # Делаем метку побольше и блочной

class CouponApplyForm(forms.Form):
    code = forms.CharField(
        label='Kod kuponu',
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Wpisz kod kuponu'})
    )

class UserCouponChoiceForm(forms.Form):
    user_coupon = forms.ModelChoiceField(
        queryset=UserCoupon.objects.none(), # Начальный пустой queryset
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="Wybierz jeden z Twoich dostępnych kuponów",
        empty_label=None, # Не показывать пустой вариант
        required=True
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None) # Получаем пользователя из kwargs
        super().__init__(*args, **kwargs)

        if user and user.is_authenticated:
            now = timezone.now() # Импортировать timezone: from django.utils import timezone
            self.fields['user_coupon'].queryset = UserCoupon.objects.filter(
                user=user,
                is_used=False,
                coupon__active=True,
                coupon__valid_from__lte=now,
                coupon__valid_to__gte=now
            ).select_related('coupon')
            # Динамическое формирование метки для каждого выбора в ModelChoiceField
            self.fields['user_coupon'].label_from_instance = lambda obj: f"{obj.coupon.code} ({obj.coupon.discount}% zniżki, ważny do {obj.coupon.valid_to.strftime('%d.%m.%Y')})"
        else:
            # Если пользователя нет, или он не аутентифицирован, оставляем queryset пустым
            # или можно скрыть поле/форму во view
            pass

class CartAddProductForm(forms.Form):
    """
    Form for adding products to the cart or updating quantities.
    """
    quantity = forms.IntegerField(
        min_value=1, 
        widget=forms.NumberInput(attrs={'class': 'form-control quantity-input-detail', 'min': '1'})
    )
    update = forms.BooleanField(required=False, initial=False, widget=forms.HiddenInput)