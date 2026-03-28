from __future__ import annotations

import smtplib
from email.message import EmailMessage

from backend.core.config import settings


class ClientPortalMailService:
    def __init__(self) -> None:
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME or settings.PORTAL_EMAIL_FROM
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = settings.SMTP_USE_TLS
        self.sender = settings.PORTAL_EMAIL_FROM
        self.firm_name = settings.CLIENT_PORTAL_FIRM_NAME

    @property
    def configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_port and self.smtp_username and self.smtp_password and self.sender)

    def send_login_code(self, *, recipient_email: str, code: str) -> None:
        if not self.configured:
            raise RuntimeError("Client portal email delivery is not configured. Add SMTP credentials to .env.")

        message = EmailMessage()
        message["Subject"] = f"{self.firm_name} client portal access code"
        message["From"] = self.sender
        message["To"] = recipient_email
        message.set_content(
            f"""Hello,

Your secure client portal access code is: {code}

This code expires in {settings.PORTAL_LOGIN_CODE_EXPIRE_MINUTES} minutes.
If you did not request this code, you can ignore this email.

Regards,
{self.firm_name}
"""
        )

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20) as server:
            if self.smtp_use_tls:
                server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(message)


client_portal_mail_service = ClientPortalMailService()
