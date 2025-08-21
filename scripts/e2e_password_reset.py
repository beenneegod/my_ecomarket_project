import os
import sys
from urllib.parse import urlparse
from pathlib import Path

# Ensure project root is on PYTHONPATH so 'config' can be imported
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.test.utils import override_settings
from django.core import mail
from django.conf import settings


def main():
    User = get_user_model()
    email = os.environ.get("TEST_RESET_EMAIL", "test.reset@example.com")
    username = os.environ.get("TEST_RESET_USERNAME", "testreset")
    password = os.environ.get("TEST_RESET_PASSWORD", "TestPass123!")

    user, created = User.objects.get_or_create(username=username, defaults={"email": email})
    if user.email != email:
        user.email = email
    user.set_password(password)
    user.is_active = True
    user.save()

    form = PasswordResetForm({"email": email})
    if not form.is_valid():
        print("FORM_ERRORS:", form.errors.as_json())
        sys.exit(1)

    parsed = urlparse(getattr(settings, "SITE_URL", "http://localhost:8000"))
    domain = parsed.netloc or "localhost:8000"
    use_https = parsed.scheme == "https"

    with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
        form.save(domain_override=domain, use_https=use_https)
        if not mail.outbox:
            print("NO_EMAIL_SENT")
            sys.exit(2)
        message = mail.outbox[-1]
        print("SUBJECT:")
        print(message.subject)
        print("BODY:")
        # Ensure consistent newlines
        print(message.body.replace('\r\n', '\n'))


if __name__ == "__main__":
    main()
