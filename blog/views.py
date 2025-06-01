from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, View # DetailView is not directly used, a custom View is.
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy # Not strictly needed here, but good for general use.
from django.contrib import messages
from .models import Post # Comment removed, F401
from .forms import CommentForm # Assuming CommentForm will be created later
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated # Или кастомный permission для API-ключа
from rest_framework.authentication import TokenAuthentication
from .serializers import PostCreateSerializer
# from .models import Post # Уже импортирован # F811 - removed duplicate import
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone
from django.conf import settings

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
                return Response({"error": "API post author not configured correctly on the server."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                # logger.error(f"Error getting API Post Author: {e}")
                return Response({"error": f"Could not determine API post author: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            title = serializer.validated_data['title']
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


            # Сохраняем пост с нужным автором и слагом
            # Мы не вызываем serializer.save() напрямую, так как нам нужно добавить author и slug.
            # Вместо этого, создаем объект Post вручную.
            try:
                post = Post.objects.create(
                    author=author,
                    title=title,
                    slug=new_slug,
                    body=serializer.validated_data['body'],
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
                    {"error": f"Failed to create post: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PostListView(ListView):
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = 5
    queryset = Post.objects.filter(status='published').select_related('author').order_by('-published_at')

class PostDetailView(View): # Inherit from View for custom GET and POST

    def get(self, request, slug, *args, **kwargs):
        post = get_object_or_404(Post, slug=slug, status='published')
        comments = post.comments.filter(active=True).select_related('author').order_by('-created_at')
        comment_form = CommentForm()
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

    def post(self, request, slug, *args, **kwargs):
        post = get_object_or_404(Post, slug=slug, status='published')
        comments = post.comments.filter(active=True).order_by('-created_at')
        comment_form = CommentForm(data=request.POST)

        if not request.user.is_authenticated:
            # Handle anonymous user trying to comment, e.g., redirect to login
            # For now, let's assume CommentForm might handle this or a LoginRequiredMixin is used on the view.
            # A simple way is to redirect to login.
            # Or, for this specific structure, prevent further processing if user is not authenticated.
            # This part of the logic depends on how strict the login requirement is for commenting.
            # The task mentions request.user, so authentication is implied for comment authorship.
            return redirect(reverse_lazy('login')) # Or your specific login URL name

        if comment_form.is_valid():
            new_comment = comment_form.save(commit=False)
            new_comment.post = post
            new_comment.author = request.user
            new_comment.save()
            return redirect(post.get_absolute_url())
        else:
            context = {
                'post': post,
                'comments': comments,
                'comment_form': comment_form, # Pass the invalid form back to display errors
            }
            return render(request, 'blog/post_detail.html', context)

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
    login_url = reverse_lazy('login') # Make sure you have a URL named 'login'

    def post(self, request, slug, *args, **kwargs):
        # Thanks to LoginRequiredMixin, request.user is guaranteed to be authenticated here.
        post = get_object_or_404(Post, slug=slug, status='published')
        comments = post.comments.filter(active=True).order_by('-created_at')
        comment_form = CommentForm(data=request.POST)

        if comment_form.is_valid():
            new_comment = comment_form.save(commit=False)
            new_comment.post = post
            new_comment.author = request.user # Assured by LoginRequiredMixin
            new_comment.save()
            return redirect(post.get_absolute_url())
        else:
            # Rerender the page with the post, existing comments, and the form with errors
            context = {
                'post': post,
                'comments': comments,
                'comment_form': comment_form,
            }
            return render(request, 'blog/post_detail.html', context)

# The subtask asks for PostDetailView(View). I will stick to that and include the authentication check
# within the post method as designed initially, rather than using LoginRequiredMixin on the class,
# to keep GET accessible to anonymous users and only protect POST.
# The `LoginProtectedPostDetailView` is an alternative if class-level protection for POST is preferred.
# Reverting to the simpler PostDetailView(View) with check inside post method.

# Final version for PostDetailView as per task description:
# (The previous PostDetailView was mostly fine, just clarifying the LoginRequired part)

class PostDetailView(View):
    def get(self, request, slug, *args, **kwargs):
        post = get_object_or_404(Post, slug=slug, status='published')
        comments = post.comments.filter(active=True).order_by('-created_at')
        comment_form = CommentForm()
        context = {
            'post': post,
            'comments': comments,
            'comment_form': comment_form,
        }
        return render(request, 'blog/post_detail.html', context)

    def post(self, request, slug, *args, **kwargs):
        post = get_object_or_404(Post, slug=slug, status='published')

        if not request.user.is_authenticated:
            messages.error(request, "Musisz być zalogowany, aby dodać komentarz.")
            return redirect(reverse_lazy('login') + f"?next={request.path}")

        # Передаем request.POST для текстовых данных и request.FILES для файлов
        comment_form = CommentForm(data=request.POST, files=request.FILES) 

        if comment_form.is_valid():
            new_comment = comment_form.save(commit=False)
            new_comment.post = post
            new_comment.author = request.user
            new_comment.save()
            messages.success(request, "Twój komentarz został dodany!")
            return redirect(post.get_absolute_url() + '#comments-section') # Перенаправляем к секции комментариев
        else:
            # Если форма невалидна, передаем ее обратно с ошибками
            # Также нужно снова получить список комментариев для корректного отображения страницы
            comments = post.comments.filter(active=True).select_related('author').order_by('-created_at')
            messages.error(request, "Popraw błędy w formularzu komentarza.")
            context = {
                'post': post,
                'comments': comments,
                'comment_form': comment_form, # Форма с ошибками
            }
            return render(request, 'blog/post_detail.html', context)
