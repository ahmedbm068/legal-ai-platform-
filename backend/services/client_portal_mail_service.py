from __future__ import annotations

import logging
import smtplib
from email.utils import parseaddr
from email.message import EmailMessage

from backend.core.config import settings

logger = logging.getLogger(__name__)


class ClientPortalMailService:
    def __init__(self) -> None:
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME or settings.PORTAL_EMAIL_FROM
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = settings.SMTP_USE_TLS
        self.smtp_timeout_seconds = max(5, int(settings.SMTP_TIMEOUT_SECONDS))
        self.sender = settings.PORTAL_EMAIL_FROM
        self.firm_name = settings.CLIENT_PORTAL_FIRM_NAME

    @property
    def configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_port and self.smtp_username and self.smtp_password and self.sender)

    def _validated_sender(self) -> str:
        sender_email = parseaddr(self.sender or "")[1]
        if not sender_email:
            raise RuntimeError("Invalid sender email (PORTAL_EMAIL_FROM).")
        return sender_email

    def send_login_code(self, *, recipient_email: str, code: str) -> str:
        if not self.configured:
            raise RuntimeError("Client portal email delivery is not configured. Add SMTP credentials to .env.")

        recipient = parseaddr(recipient_email)[1]
        if not recipient:
            raise RuntimeError("Invalid recipient email address.")

        sender = self._validated_sender()

        message = EmailMessage()
        message["Subject"] = f"{self.firm_name} client portal access code"
        message["From"] = sender
        message["To"] = recipient
        message.set_content(
            f"""Hello,

Your secure client portal access code is: {code}

This code expires in {settings.PORTAL_LOGIN_CODE_EXPIRE_MINUTES} minutes.
If you did not request this code, you can ignore this email.

Regards,
{self.firm_name}
"""
        )

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.smtp_timeout_seconds) as server:
                server.ehlo()
                if self.smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(message)
        except smtplib.SMTPException as exc:
            logger.warning("SMTP delivery failed for portal login code to %s: %s", recipient, exc)
            raise RuntimeError("SMTP delivery failed for the portal login code.") from exc

        return "smtp"


client_portal_mail_service = ClientPortalMailService()
