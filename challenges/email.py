from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from common.mail import send_email


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

    send_email(subject=subject, to=[user_email], text=text_body, html=html_body, fail_silently=True)
