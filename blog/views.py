from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.template.loader import render_to_string
from django.views.generic import ListView, View # DetailView is not directly used, a custom View is.
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy # Not strictly needed here, but good for general use.
from django.contrib import messages
from .models import Post, Comment, CommentRating, BlogBan
from .forms import CommentForm # Assuming CommentForm will be created later
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated # Или кастомный permission для API-ключа
from rest_framework.authentication import TokenAuthentication
from .serializers import PostCreateSerializer
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.db.models import Avg, Count, Subquery, OuterRef, Value, IntegerField, Q
import re

User = get_user_model()

class CreatePostAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PostCreateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # Получаем автора из настроек
                author_username = settings.API_POST_AUTHOR_USERNAME
                author = User.objects.get(username=author_username)
            except User.DoesNotExist:
                # Логируем ошибку или возвращаем 500, если системный автор не найден
                # logger.error(f"API Post Author '{author_username}' not found!")
                return Response({"error": "Autor API posta nie jest poprawnie skonfigurowany na serwerze."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                # logger.error(f"Error getting API Post Author: {e}")
                return Response({"error": f"Nie można ustalić autora posta API: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            title = serializer.validated_data['title']
            # Remove leading markdown hashes from titles like "## Title"
            title = re.sub(r"^\s*#{1,6}\s+", "", title or "").strip()
            new_slug = slugify(title)
            # Проверка на уникальность слага и добавление суффикса, если необходимо
            original_slug = new_slug
            counter = 1
            while Post.objects.filter(slug=new_slug).exists():
                new_slug = f"{original_slug}-{counter}"
                counter += 1
            
            # Устанавливаем published_at, если не передано или если хотим текущее время
            published_at = serializer.validated_data.get('published_at', timezone.now())
            # Устанавливаем статус, если не передан
            post_status = serializer.validated_data.get('status', 'published')


            # Sanitize heading hashes in body as well (best effort)
            body = serializer.validated_data['body']
            body = re.sub(r"^(\s{0,3})#{1,6}(\s+)", r"\1\2", body or "", flags=re.MULTILINE)

            # Сохраняем пост с нужным автором и слагом
            # Мы не вызываем serializer.save() напрямую, так как нам нужно добавить author и slug.
            # Вместо этого, создаем объект Post вручную.
            try:
                post = Post.objects.create(
                    author=author,
                    title=title,
                    slug=new_slug,
                    body=body,
                    image=serializer.validated_data.get('image'), # get, так как image опционально
                    status=post_status,
                    published_at=published_at
                )
                # Возвращаем данные созданного поста (можно использовать другой сериализатор для ответа)
                # Для простоты вернем только ID и slug
                return Response(
                    {"id": post.id, "slug": post.slug, "title": post.title},
                    status=status.HTTP_201_CREATED
                )
            except Exception as e:
                return Response(
                    {"error": f"Nie udało się utworzyć wpisu: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@method_decorator(cache_page(300), name='dispatch')
class PostListView(ListView):
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = 5
    queryset = Post.objects.filter(status='published').order_by('-published_at')

class PostDetailView(View): # Inherit from View for custom GET and POST

    def get(self, request, slug, *args, **kwargs):
        post = get_object_or_404(Post, slug=slug, status='published')
        comments_qs = post.comments.filter(active=True)
        comments_qs = comments_qs.annotate(
            rating_avg=Avg('ratings__value'),
            rating_count=Count('ratings')
        )
        if request.user.is_authenticated:
            user_rating_sq = CommentRating.objects.filter(comment=OuterRef('pk'), user=request.user).values('value')[:1]
            comments_qs = comments_qs.annotate(user_rating_value=Subquery(user_rating_sq, output_field=IntegerField()))
        comments = comments_qs.order_by('-created_at')
        comment_form = CommentForm(request=request)
        context = {
            'post': post,
            'comments': comments,
            'comment_form': comment_form,
        }
        return render(request, 'blog/post_detail.html', context)

    def post(self, request, slug, *args, **kwargs):
        post = get_object_or_404(Post, slug=slug, status='published')
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            request.headers.get('x-requested-with') == 'XMLHttpRequest' or
            request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
        )

        # Basic IP detection
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')

        # Ban check
        now = timezone.now()
        ban_q = BlogBan.objects.filter(active=True).filter(
            Q(user=request.user) | Q(ip_address=ip)
        )
        if ban_q.filter(Q(until__isnull=True) | Q(until__gt=now)).exists():
            msg = 'Twoje konto lub IP jest zablokowane.'
            return JsonResponse({'ok': False, 'error': msg}, status=403) if is_ajax else HttpResponseForbidden(msg)

        if not request.user.is_authenticated:
            if is_ajax:
                return JsonResponse({'ok': False, 'error': 'Musisz być zalogowany, aby dodać komentarz.'}, status=401)
            return redirect(reverse_lazy('login') + f"?next={request.path}")

        # Honeypot: hidden field should stay empty
        honeypot = (request.POST.get('website') or '').strip()  # name chosen to look legit
        if honeypot:
            # Silently drop or respond as success without creating
            return JsonResponse({'ok': True, 'html': '', 'count': post.comments.filter(active=True).count()}) if is_ajax else redirect(post.get_absolute_url() + '#comments-section')

        # Rate limit: max N comments per window per user or IP
        WINDOW = timedelta(minutes=2)
        MAX_COMMENTS = 3
        since = now - WINDOW
        recent_q = Comment.objects.filter(post=post, created_at__gte=since)
        if request.user.is_authenticated:
            recent_q = recent_q.filter(author=request.user)
        elif ip:
            recent_q = recent_q.filter(ip_address=ip)
        if recent_q.count() >= MAX_COMMENTS:
            msg = 'Za dużo komentarzy. Spróbuj za chwilę.'
            return JsonResponse({'ok': False, 'error': msg}, status=429) if is_ajax else HttpResponseBadRequest(msg)

        comment_form = CommentForm(data=request.POST, files=request.FILES, request=request)

        if comment_form.is_valid():
            new_comment = comment_form.save(commit=False)
            new_comment.post = post
            new_comment.author = request.user
            new_comment.ip_address = ip
            new_comment.save()

            if is_ajax:
                # For newly created comment, bootstrap aggregate fields for the template
                new_comment.rating_avg = 0
                new_comment.rating_count = 0
                new_comment.user_rating_value = None
                item_html = render_to_string('blog/_comment_item.html', {'comment': new_comment}, request=request)
                count = post.comments.filter(active=True).count()
                return JsonResponse({'ok': True, 'html': item_html, 'count': count})

            return redirect(post.get_absolute_url() + '#comments-section')
        else:
            if is_ajax:
                return JsonResponse({'ok': False, 'errors': comment_form.errors}, status=400)

            comments = post.comments.filter(active=True).order_by('-created_at')
            context = {
                'post': post,
                'comments': comments,
                'comment_form': comment_form,
            }
            return render(request, 'blog/post_detail.html', context)

    # For POST, we can wrap the method with LoginRequiredMixin's dispatch or use function decorator
    # For simplicity, we'll assume the form/template handles login checks,
    # or LoginRequiredMixin is added to the class if the whole view needs protection.
    # However, to properly use LoginRequiredMixin for the post method, it's better to apply it to the class
    # and then the dispatch method will handle the login check.
    # Let's make the class inherit from LoginRequiredMixin for the POST part.
    # But this would protect GET as well, which might not be desired.
    # A common pattern is to have separate views or check request.user.is_authenticated in post.

    # For this task, let's make the POST require login by checking request.user.is_authenticated.
    # If a more robust mixin approach is needed, the view can be split or LoginRequiredMixin applied to the class.

    # (POST handling is implemented in the final PostDetailView class below)

# If the entire PostDetailView should be login protected for POSTing comments,
# the class definition could be: class PostDetailView(LoginRequiredMixin, View):
# And then LoginRequiredMixin's settings like login_url can be configured.
# The current implementation of post method manually checks request.user.is_authenticated
# and redirects to login. This is a valid approach.
# The original prompt mentioned "ensure user is authenticated or handle anonymous comments".
# I've chosen to ensure authentication for comment submission.
# If LoginRequiredMixin is added to the class:
# class PostDetailView(LoginRequiredMixin, View):
#    login_url = reverse_lazy('login') # or your actual login url
#    # ... get and post methods ...
#    # In the post method, request.user would then be guaranteed to be authenticated.

# For a cleaner approach with LoginRequiredMixin specifically for the POST:
# One way is to use a method decorator if it were a function-based view.
# For class-based views, you can override `dispatch`.

class LoginProtectedPostDetailView(LoginRequiredMixin, PostDetailView):
    login_url = reverse_lazy('login')

# The subtask asks for PostDetailView(View). I will stick to that and include the authentication check
# within the post method as designed initially, rather than using LoginRequiredMixin on the class,
# to keep GET accessible to anonymous users and only protect POST.
# The `LoginProtectedPostDetailView` is an alternative if class-level protection for POST is preferred.
# Reverting to the simpler PostDetailView(View) with check inside post method.

# Final version for PostDetailView as per task description:
# (The previous PostDetailView was mostly fine, just clarifying the LoginRequired part)

 


def rate_comment(request, comment_id: int):
    if request.method != 'POST':
        return HttpResponseBadRequest('Nieprawidłowe żądanie')
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Musisz być zalogowany, aby oceniać.'}, status=401)
    try:
        comment = Comment.objects.select_related('author', 'post').get(pk=comment_id, active=True)
    except Comment.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Komentarz nie istnieje.'}, status=404)
    if comment.author_id == request.user.id:
        return JsonResponse({'ok': False, 'error': 'Nie możesz oceniać własnego komentarza.'}, status=400)

    # Read value from POST (supports form or JSON)
    try:
        if request.headers.get('Content-Type', '').startswith('application/json'):
            import json
            payload = json.loads(request.body or '{}')
            value = int(payload.get('value'))
        else:
            value = int(request.POST.get('value'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Brak lub niepoprawna wartość oceny.'}, status=400)

    if value not in (1, 2, 3, 4, 5):
        return JsonResponse({'ok': False, 'error': 'Ocena musi być w zakresie 1-5.'}, status=400)

    # Create or update rating
    obj, created = CommentRating.objects.update_or_create(
        comment=comment, user=request.user,
        defaults={'value': value}
    )

    # Compute aggregates
    agg = comment.ratings.aggregate(avg=Avg('value'), cnt=Count('id'))
    avg = agg['avg'] or 0
    cnt = agg['cnt'] or 0
    return JsonResponse({'ok': True, 'average': round(avg, 2), 'count': cnt, 'your_value': value})
