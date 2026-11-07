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


def _check_configured():
    if not is_configured():
        raise MailNotConfigured(
            "Email is not configured. Set SGP_MAIL_ENABLED and the SMTP settings."
        )


def _deliver(message):
    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=15) as server:
        server.starttls()
        if MAIL_USERNAME:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(message)


def send_report_card(recipient, student_name, subject, html, pdf_bytes=None):
    """Send a report card email with an optional PDF attachment."""
    _check_configured()

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

    _deliver(message)


def send_alert(recipient, student_name, html):
    """Send a guardian alert email about a student who needs attention."""
    _check_configured()

    message = EmailMessage()
    message["From"] = MAIL_SENDER
    message["To"] = recipient
    message["Subject"] = f"Academic alert for {student_name}"
    message.set_content(f"An academic alert was raised for {student_name}.")
    message.add_alternative(html, subtype="html")

    _deliver(message)
