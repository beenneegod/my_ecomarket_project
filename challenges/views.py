# challenges/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count, F
from django.db import transaction # Для атомарных операций
from .models import Challenge, UserChallengeParticipation, Badge, UserBadge
from store.models import Profile, UserCoupon # Обновленный импорт
from .forms import ChallengeParticipationForm # Если вы создали этот файл
from django.views.decorators.http import require_POST

def challenge_list_view(request):
    today = timezone.now()

    # Фильтруем челленджи, чтобы показывать только активные и не являющиеся шаблонами
    all_challenges = Challenge.objects.filter(
        is_active=True, 
        is_template=False
    )
    # Исключаем челленджи без slug (slug пустой или None)
    all_challenges = all_challenges.exclude(slug__isnull=True).exclude(slug="")

    upcoming_challenges = all_challenges.filter(start_date__gt=today).order_by('start_date')
    active_challenges = all_challenges.filter(start_date__lte=today, end_date__gte=today).order_by('start_date')

    user_participations_ids = set()
    if request.user.is_authenticated:
        participations = UserChallengeParticipation.objects.filter(user=request.user)
        user_participations_ids = set(p.challenge_id for p in participations)

    context = {
        'upcoming_challenges': upcoming_challenges,
        'active_challenges': active_challenges,
        'user_participations_ids': user_participations_ids,
        'page_title': 'Eko-wyzwania',
    }
    return render(request, 'challenges/challenge_list.html', context)

def challenge_detail_view(request, slug):
    challenge = get_object_or_404(Challenge, slug=slug)
    participation = None
    can_mark_as_done = False # Может ли пользователь отметить выполнение сейчас
    form_for_completion = None # Форма для отчета о выполнении (если есть)

    if request.user.is_authenticated:
        try:
            participation = UserChallengeParticipation.objects.get(user=request.user, challenge=challenge)
            if participation.status in ['joined', 'in_progress'] and challenge.is_active_now():
                can_mark_as_done = True
        except UserChallengeParticipation.DoesNotExist:
            pass # Пользователь еще не участвует или его участие было удалено

    if can_mark_as_done and request.method == 'POST':
        # Проверяем, была ли нажата кнопка "Отметить как выполненный"
        # В шаблоне у этой кнопки должно быть name="mark_completed_action"
        if 'mark_completed_action' in request.POST:
            # Если используется форма для отчета
            if ChallengeParticipationForm: # Проверяем, существует ли класс формы
                form_for_completion = ChallengeParticipationForm(request.POST, request.FILES, instance=participation)
                if form_for_completion.is_valid():
                    with transaction.atomic():
                        updated_participation = form_for_completion.save(commit=False)
                        updated_participation.status = 'completed_approved' # Пока авто-подтверждение
                        updated_participation.completed_at = timezone.now()
                        updated_participation.save()

                        # Начисление очков
                        profile, created = Profile.objects.get_or_create(user=request.user)
                        profile.eco_points = F('eco_points') + challenge.points_for_completion
                        profile.last_points_update = timezone.now()
                        profile.save()

                        success_message = f"Pomyślnie ukończyłeś wyzwanie '{challenge.title}'! Otrzymano: {challenge.points_for_completion} пунктов"
                        
                        # Выдача значка (если есть)
                        if challenge.badge_name_reward: # Используем поле из Challenge
                            badge, badge_created = Badge.objects.get_or_create(
                                name=challenge.badge_name_reward,
                                defaults={'icon_class': challenge.badge_icon_class_reward or 'bi bi-patch-check-fill'}
                            )
                            UserBadge.objects.get_or_create(
                                user=request.user,
                                badge=badge
                                # defaults={'challenge_source': challenge} # Поле отсутствует в модели UserBadge
                            )
                            success_message += f" i odznakę '{badge.name}'"
                        
                        # Выдача купона (если есть)
                        if challenge.reward_coupon and challenge.reward_coupon.active:
                            UserCoupon.objects.get_or_create(
                                user=request.user,
                                coupon=challenge.reward_coupon,
                                defaults={
                                    'challenge_source': challenge,
                                    'is_used': False # Явно указываем, что купон не использован
                                }
                            )
                            coupon_code = challenge.reward_coupon.code
                            success_message += f". Twój kod rabatowy: {coupon_code}"
                            # Опционально: можно создать запись UserCoupon, если такая модель будет

                        success_message += "."
                        messages.success(request, success_message)
                        
                        return redirect(challenge.get_absolute_url()) # Перезагружаем страницу деталей
                # else: форма не валидна, она будет передана в контекст ниже
            else: # Если форма не используется, просто меняем статус
                with transaction.atomic():
                    participation.status = 'completed_approved' # Пока авто-подтверждение
                    participation.completed_at = timezone.now()
                    participation.save()
                    
                    profile, created = Profile.objects.get_or_create(user=request.user)
                    profile.eco_points = F('eco_points') + challenge.points_for_completion
                    profile.last_points_update = timezone.now()
                    profile.save()

                    success_message = f"Pomyślnie ukończyłeś wyзwanie '{challenge.title}'! Оtrzymano: {challenge.points_for_completion} пунктов"

                    if challenge.badge_name_reward:
                        badge, badge_created = Badge.objects.get_or_create(name=challenge.badge_name_reward, defaults={'icon_class': challenge.badge_icon_class_reward or 'bi bi-patch-check-fill'})
                        UserBadge.objects.get_or_create(user=request.user, badge=badge) # Поле challenge_source отсутствует
                        success_message += f" i odznakę '{badge.name}'"

                    # Выдача купона (если есть)
                    if challenge.reward_coupon and challenge.reward_coupon.active:
                        UserCoupon.objects.get_or_create(
                            user=request.user,
                            coupon=challenge.reward_coupon,
                            defaults={
                                'challenge_source': challenge,
                                'is_used': False # Явно указываем, что купон не использован
                            }
                        )
                        coupon_code = challenge.reward_coupon.code
                        success_message += f". Twój kod rabatowy: {coupon_code}"
                        # Опционально: можно создать запись UserCoupon, если такая модель будет
                    
                    success_message += "."
                    messages.success(request, success_message)
                    return redirect(challenge.get_absolute_url())
    
    if can_mark_as_done and not form_for_completion: # Если не было POST или форма не была создана из-за ошибки
        if ChallengeParticipationForm:
            form_for_completion = ChallengeParticipationForm(instance=participation) # Пустая форма для GET

    context = {
        'challenge': challenge,
        'participation': participation,
        'can_mark_as_done': can_mark_as_done,
        'completion_form': form_for_completion, # Передаем форму в контекст
        'page_title': challenge.title,
    }
    return render(request, 'challenges/challenge_detail.html', context)

@login_required
def join_challenge_view(request, challenge_id):
    challenge = get_object_or_404(Challenge, id=challenge_id)
    
    if not challenge.can_join_now():
        messages.error(request, "Nie możesz dołączyć do tego wyzwania teraz (nie jest aktywne lub zostało zakończone).")
        return redirect(reverse('challenges:challenge_list')) # Используем reverse для большей гибкости

    # Проверяем, не завершил ли пользователь уже этот челлендж
    existing_participation = UserChallengeParticipation.objects.filter(user=request.user, challenge=challenge).first()
    if existing_participation and existing_participation.status in ['completed_approved', 'completed_pending_review']:
        messages.info(request, f"Już ukończyłeś lub oczekujesz na weryfikację wyzwania: '{challenge.title}'.")
        return redirect(challenge.get_absolute_url())

    participation, created = UserChallengeParticipation.objects.get_or_create(
        user=request.user,
        challenge=challenge,
        defaults={'status': 'joined'} # При первом присоединении
    )
    
    if created:
        messages.success(request, f"Pomyślnie dołączyłeś do wyzwania: '{challenge.title}'!")
    else:
        # Если участие уже есть, но статус другой (например, failed), можно его "перезапустить"
        if participation.status != 'joined' and participation.status != 'in_progress':
            participation.status = 'joined'
            participation.completed_at = None # Сбрасываем дату выполнения
            participation.user_notes = "" # Очищаем заметки
            participation.save()
            messages.info(request, f"Ponownie dołączyłeś do wyzwania: '{challenge.title}'. Powodzenia!")
        else:
            messages.info(request, f"Już bierzesz udział w wyzwaniu: '{challenge.title}'.")
            
    return redirect(challenge.get_absolute_url())


@login_required
def my_progress_view(request):
    user = request.user
    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        # Если профиля нет, можно его создать или показать сообщение
        # Для простоты, предположим, что сигнал create_or_update_user_profile в store/signals.py работает
        # и создает профиль при регистрации. Если нет, здесь нужна обработка.
        profile, _ = Profile.objects.get_or_create(user=user) # Создаем, если нет

    active_participations = UserChallengeParticipation.objects.filter(
        user=user, 
        status__in=['joined', 'in_progress'],
        challenge__end_date__gte=timezone.now() # Показываем только те, что еще не закончились
    ).select_related('challenge').order_by('challenge__end_date')
    
    completed_participations = UserChallengeParticipation.objects.filter(
        user=user,
        status__in=['completed_approved', 'completed_pending_review']
    ).select_related('challenge').order_by('-completed_at', '-challenge__end_date')
    
    earned_badges = UserBadge.objects.filter(user=user).select_related('badge').order_by('-awarded_at')
    
    # Получаем купоны пользователя
    user_coupons = UserCoupon.objects.filter(user=user).select_related('coupon', 'challenge_source').order_by('-awarded_at')

    context = {
        'profile': profile,
        'active_participations': active_participations,
        'completed_participations': completed_participations,
        'earned_badges': earned_badges,
        'user_coupons': user_coupons, # Добавляем купоны в контекст
        'current_time': timezone.now(), # Добавляем текущее время для сравнения в шаблоне
        'page_title': 'Moje postępy w wyzwaniach',
    }
    return render(request, 'challenges/my_progress.html', context)


def leaderboard_view(request):
    # Топ пользователей по очкам. Используем select_related для оптимизации запроса к user.
    top_profiles = Profile.objects.filter(eco_points__gt=0).select_related('user').order_by('-eco_points', 'last_points_update')[:20] 

    # Добавляем ранг для отображения
    leaderboard_entries = []
    for i, profile_entry in enumerate(top_profiles):
        leaderboard_entries.append({
            'rank': i + 1,
            'user': profile_entry.user,
            'eco_points': profile_entry.eco_points,
            'avatar_url': profile_entry.avatar_url # Используем avatar_url из Profile
        })

    context = {
        'leaderboard_entries': leaderboard_entries,
        'page_title': 'Leaderboard Eko-wyzwań',
        'description': 'Zobacz, kto zdobył najwięcej punktów w naszych eko-wyzwaniach! Tutaj znajdziesz najlepszych uczestników, którzy aktywnie dbają o środowisko i zdobywają eko-punkty za swoje działania.',
    }
    return render(request, 'challenges/leaderboard.html', context)