from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import gettext as _


def notify_challenge_review(user_email: str, challenge_title: str, approved: bool, notes: str | None = None):
    if not user_email:
        return
    subject = (
        _("Twoje zgłoszenie wyzwania zostało zaakceptowane: %(title)s") % {"title": challenge_title}
        if approved else
        _("Twoje zgłoszenie wyzwania zostało odrzucone: %(title)s") % {"title": challenge_title}
    )
    context = {"challenge_title": challenge_title, "notes": notes}
    if approved:
        text_body = render_to_string("challenges/emails/review_approved.txt", context)
        html_body = render_to_string("challenges/emails/review_approved.html", context)
    else:
        text_body = render_to_string("challenges/emails/review_rejected.txt", context)
        html_body = render_to_string("challenges/emails/review_rejected.html", context)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None) or 'no-reply@example.com'
    try:
        msg = EmailMultiAlternatives(subject, text_body, from_email, [user_email])
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)
    except Exception:
        # Swallow errors to not break admin action flow
        pass
