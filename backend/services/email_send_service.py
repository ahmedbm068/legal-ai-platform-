from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import parseaddr

from backend.core.config import settings


class EmailSendService:
    def send_email(self, *, to: str, subject: str, body_html: str, body_text: str, cc: list[str]) -> str:
        if not settings.SMTP_PASSWORD:
            return "simulated"

        recipient = parseaddr(to)[1]
        if not recipient:
            raise RuntimeError("Invalid recipient email address.")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.PORTAL_EMAIL_FROM
        message["To"] = recipient
        if cc:
            message["Cc"] = ", ".join(cc)
        message.set_content(body_text or "Please view this message in an HTML-capable email client.")
        if body_html:
            message.add_alternative(body_html, subtype="html")

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USERNAME or settings.PORTAL_EMAIL_FROM, settings.SMTP_PASSWORD)
            server.send_message(message)
        return "smtp"


email_send_service = EmailSendService()
