from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, View # DetailView is not directly used, a custom View is.
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy # Not strictly needed here, but good for general use.
from django.contrib import messages
from .models import Post, Comment
from .forms import CommentForm # Assuming CommentForm will be created later

class PostListView(ListView):
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = 5
    queryset = Post.objects.filter(status='published').order_by('-published_at')

class PostDetailView(View): # Inherit from View for custom GET and POST

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
            comments = post.comments.filter(active=True).order_by('-created_at')
            messages.error(request, "Popraw błędy w formularzu komentarza.")
            context = {
                'post': post,
                'comments': comments,
                'comment_form': comment_form, # Форма с ошибками
            }
            return render(request, 'blog/post_detail.html', context)
