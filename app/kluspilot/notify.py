import smtplib
from email.message import EmailMessage
from typing import Optional

from .config import settings


def smtp_configured() -> bool:
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_PORT
        and settings.SMTP_USER
        and settings.SMTP_PASS
        and settings.NOTIFY_FROM
    )


def send_lead_email(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> None:
    """
    Sends an email using SMTP settings from .env.
    If SMTP is not configured, this function silently does nothing.
    """
    if not smtp_configured():
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.NOTIFY_FROM
    msg["To"] = to_email
    msg.set_content(text_body)

    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, int(settings.SMTP_PORT)) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)