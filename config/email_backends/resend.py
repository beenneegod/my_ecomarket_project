"""Django email backend for Resend API.

Usage:
    EMAIL_BACKEND = 'config.email_backends.resend.ResendEmailBackend'
    RESEND_API_KEY = '<your key>'

Supports: to/cc/bcc, reply-to, text and HTML bodies, simple attachments (optional).
"""
from __future__ import annotations

import base64
import logging
from typing import List, Optional

import httpx
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    api_url = "https://api.resend.com/emails"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key: Optional[str] = getattr(settings, "RESEND_API_KEY", None)

    def send_messages(self, email_messages: List[EmailMessage]) -> int:
        if not email_messages:
            return 0
        if not self.api_key:
            logger.error("RESEND_API_KEY is not configured; cannot send emails.")
            return 0
        sent = 0
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = getattr(settings, "EMAIL_TIMEOUT", 60)
        from_email_default = getattr(settings, "DEFAULT_FROM_EMAIL", None)

        with httpx.Client(timeout=timeout) as client:
            for msg in email_messages:
                try:
                    from_email = msg.from_email or from_email_default
                    if not from_email:
                        logger.warning("Email skipped: missing from email and DEFAULT_FROM_EMAIL")
                        continue
                    # Determine text/html bodies
                    text_body = msg.body or None
                    html_body = None
                    # Django stores alternatives as list of (content, mimetype)
                    for content, mimetype in getattr(msg, "alternatives", []) or []:
                        if mimetype == "text/html":
                            html_body = content
                    # If only html was provided via EmailMultiAlternatives, body might be text; we keep both if present

                    payload = {
                        "from": from_email,
                        "to": list(msg.to or []),
                        "subject": msg.subject or "",
                    }
                    if getattr(msg, "cc", None):
                        payload["cc"] = list(msg.cc)
                    if getattr(msg, "bcc", None):
                        payload["bcc"] = list(msg.bcc)
                    # reply_to expects list of strings
                    if getattr(msg, "reply_to", None):
                        payload["reply_to"] = list(msg.reply_to)
                    if html_body:
                        payload["html"] = html_body
                    if text_body:
                        payload["text"] = text_body

                    # Attachments (optional): Resend expects list of {filename, content}
                    attachments_payload = []
                    for attachment in getattr(msg, "attachments", []) or []:
                        try:
                            if isinstance(attachment, tuple) and len(attachment) in (2, 3):
                                filename = attachment[0]
                                content = attachment[1]
                                if hasattr(content, "read"):
                                    content = content.read()
                                if isinstance(content, str):
                                    content_bytes = content.encode("utf-8")
                                else:
                                    content_bytes = content
                                attachments_payload.append(
                                    {
                                        "filename": filename,
                                        "content": base64.b64encode(content_bytes).decode("ascii"),
                                    }
                                )
                        except Exception as ex:  # noqa: BLE001
                            logger.warning("Skipping attachment due to error: %s", ex)
                    if attachments_payload:
                        payload["attachments"] = attachments_payload

                    resp = client.post(self.api_url, headers=headers, json=payload)
                    if resp.status_code >= 200 and resp.status_code < 300:
                        sent += 1
                    else:
                        logger.error("Resend API error %s: %s", resp.status_code, resp.text)
                except Exception as e:  # noqa: BLE001
                    if not self.fail_silently:
                        raise
                    logger.exception("Failed to send email via Resend: %s", e)
        return sent
