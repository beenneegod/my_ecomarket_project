# config/urls.py
from django.contrib import admin

# Ustawienia polskich tytułów w panelu administracyjnym
admin.site.site_header = "Panel administracyjny EcoMarket"
admin.site.site_title = "EcoMarket Admin"
admin.site.index_title = "Zarządzanie serwisem"
from django.conf import settings # Импортируем настройки
from django.conf.urls.static import static # Импортируем помощник для статики/медиа
from store import views as store_views
from django.contrib.auth import views as auth_views # Импортируем auth_views
from store.forms import CustomAuthenticationForm, CustomPasswordResetForm, CustomSetPasswordForm
from django.urls import path, include, reverse_lazy
from django.http import HttpResponse  # <-- добавить


urlpatterns = [
    path('admin/', admin.site.urls),
    # Healthcheck для Railway
    path('healthz/', lambda r: HttpResponse('ok'), name='healthz'),  # <-- добавить
    path('', store_views.homepage, name='homepage'),
    path('store/', include('store.urls', namespace='store')),
    path('payments/', include('payments.urls', namespace='payments')),
    path('blog/', include('blog.urls', namespace='blog')), # Added blog URLs
    path('accounts/login/', auth_views.LoginView.as_view(
            template_name='registration/login.html',
            authentication_form=CustomAuthenticationForm 
        ), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(
            template_name='registration/logged_out.html'
        ), name='logout'),

    path('accounts/register/', store_views.register, name='register'),
    path('accounts/password_reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.html', # Текстовый шаблон для email
        subject_template_name='registration/password_reset_subject.txt', # Шаблон для темы письма (создадим)
        form_class=CustomPasswordResetForm, # <--- Используем нашу форму
        success_url=reverse_lazy('password_reset_done') # Используем reverse_lazy для success_url
    ), name='password_reset'),
    path('accounts/password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        form_class=CustomSetPasswordForm, # <--- Используем нашу форму
        success_url=reverse_lazy('password_reset_complete')
    ), name='password_reset_confirm'),
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),
    path('accounts/password_change/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change_form.html',
        success_url=reverse_lazy('password_change_done')
    ), name='password_change'),
    path('accounts/password_change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done.html'
    ), name='password_change_done'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('eco-calculator/', include('carbon_calculator.urls', namespace='carbon_calculator')),
    path('eco-challenges/', include('challenges.urls', namespace='challenges')),
    path('eco-places/', include('places.urls', namespace='places')),
    path('chat/', include('chat.urls', namespace='chat')),
]

# В режиме разработки (DEBUG=True) добавляем обработку медиа-файлов
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    #urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)