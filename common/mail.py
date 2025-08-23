"""Project-wide simple email helper that uses Django's current email backend.

This keeps calling code agnostic of SMTP vs Resend.
"""
from __future__ import annotations

from typing import Iterable, Optional
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings


def send_email(
    *,
    subject: str,
    to: Iterable[str],
    text: Optional[str] = None,
    html: Optional[str] = None,
    from_email: Optional[str] = None,
    cc: Optional[Iterable[str]] = None,
    bcc: Optional[Iterable[str]] = None,
    reply_to: Optional[Iterable[str]] = None,
    fail_silently: bool = True,
) -> int:
    if not to:
        return 0
    from_email = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', None)
    connection = get_connection()
    msg = EmailMultiAlternatives(
        subject=subject or "",
        body=text or "",
        from_email=from_email,
        to=list(to),
        cc=list(cc or []),
        bcc=list(bcc or []),
        reply_to=list(reply_to or []),
        connection=connection,
    )
    if html:
        msg.attach_alternative(html, "text/html")
    return msg.send(fail_silently=fail_silently)
