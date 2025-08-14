"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

django_app = get_asgi_application()

# Import routing after Django is initialized to avoid AppRegistryNotReady
from chat.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
	'http': django_app,
	'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
