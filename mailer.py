"""Optional email delivery for report cards.

Disabled unless MAIL_ENABLED is set and SMTP details are provided, so the app
never attempts to send mail in local development.
"""

import smtplib
from email.message import EmailMessage

from config import (
    MAIL_ENABLED,
    MAIL_PASSWORD,
    MAIL_PORT,
    MAIL_SENDER,
    MAIL_SERVER,
    MAIL_USERNAME,
)


class MailNotConfigured(RuntimeError):
    """Raised when email is requested but SMTP settings are missing."""


def is_configured():
    return bool(MAIL_ENABLED and MAIL_SERVER and MAIL_SENDER)


def send_report_card(recipient, student_name, subject, html, pdf_bytes=None):
    """Send a report card email with an optional PDF attachment."""
    if not is_configured():
        raise MailNotConfigured(
            "Email is not configured. Set SGP_MAIL_ENABLED and the SMTP settings."
        )

    message = EmailMessage()
    message["From"] = MAIL_SENDER
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(f"Report card for {student_name}. Please view the attached file.")
    message.add_alternative(html, subtype="html")
    if pdf_bytes:
        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=f"{student_name}-report-card.pdf",
        )

    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=15) as server:
        server.starttls()
        if MAIL_USERNAME:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(message)
