from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from .models import Post

User = get_user_model()


class CreatePostAPITests(TestCase):
	def setUp(self):
		# API caller (any authenticated user)
		self.api_user = User.objects.create_user(username="api_caller", password="pass12345")
		self.api_token = Token.objects.create(user=self.api_user)

		# Ensure configured author exists (default: 'default_api_user')
		self.author_user = User.objects.create_user(username="default_api_user", password="pass12345")

		self.client = APIClient()
		self.url = reverse('blog:api_create_post')

	def test_create_post_success(self):
		# Authenticate as api_user; the author used will be settings.API_POST_AUTHOR_USERNAME
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.api_token.key}')
		payload = {
			"title": "## AI Generated Insights on Ecology",
			"body": "# Intro\n## Subheading\nContent body.",
			"status": "published",
		}

		resp = self.client.post(self.url, data=payload, format='json')
		self.assertEqual(resp.status_code, 201, msg=resp.content)
		data = resp.json()
		self.assertIn('id', data)
		self.assertIn('slug', data)
		self.assertIn('title', data)

		post = Post.objects.get(id=data['id'])
		# Title should have leading markdown hashes stripped
		self.assertTrue(post.title.startswith('AI Generated'), post.title)
		# Body top-level heading hashes should be sanitized at least at start of lines
		self.assertNotRegex(post.body.splitlines()[0], r"^\s*#")
		self.assertEqual(post.status, 'published')
		self.assertEqual(post.author.username, 'default_api_user')

	def test_auth_required(self):
		payload = {"title": "AI Ecology", "body": "Content"}
		resp = self.client.post(self.url, data=payload, format='json')
		self.assertIn(resp.status_code, (401, 403))

	@override_settings(API_POST_AUTHOR_USERNAME='nonexistent_author_123')
	def test_missing_configured_author_returns_500(self):
		# Still authenticate the caller
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.api_token.key}')
		payload = {"title": "AI Ecology Deep Dive", "body": "Content"}
		resp = self.client.post(self.url, data=payload, format='json')
		self.assertEqual(resp.status_code, 500)
		self.assertIn('error', resp.json())

