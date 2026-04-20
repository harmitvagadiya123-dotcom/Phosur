"""
Email Service — Sends HTML lead notification emails via Gmail SMTP.

Uses stdlib smtplib + email.mime (zero external dependencies).
Authenticates with Gmail App Password (not OAuth2) for simplicity.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

logger = logging.getLogger(__name__)

# Load HTML template once at module level
_TEMPLATE_PATH = Path(__file__).parent / "email_template.html"
_EMAIL_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")


def send_lead_email(lead_data: dict) -> bool:
    """
    Send a high-intent lead notification email.

    Args:
        lead_data: Dict with keys: NAME, COUNTRY, DESIGNATIONORCOMPANY,
                   DATE, SNO, BuyingIntent, ConversationHistory, LINKEDIN

    Returns:
        True if email sent successfully, False otherwise.
    """
    smtp_email = os.environ.get("SMTP_EMAIL", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    notify_to = os.environ.get("NOTIFY_TO", "harmitvagadiya123@gmail.com")
    notify_cc = os.environ.get("NOTIFY_CC", "harmitvagadiya123@gmail.com")

    if not smtp_email or not smtp_password:
        logger.error("SMTP_EMAIL or SMTP_PASSWORD not configured")
        return False

    # Build subject
    name = lead_data.get("NAME", "Unknown")
    country = lead_data.get("COUNTRY", "Unknown")
    subject = f"🔥 High Intent Lead: {name} From {country}"

    # Render HTML body
    html_body = _EMAIL_TEMPLATE.format(
        NAME=lead_data.get("NAME", ""),
        COUNTRY=lead_data.get("COUNTRY", ""),
        DESIGNATIONORCOMPANY=lead_data.get("DESIGNATIONORCOMPANY", ""),
        DATE=lead_data.get("DATE", ""),
        SNO=lead_data.get("SNO", ""),
        BuyingIntent=lead_data.get("BuyingIntent", ""),
        ConversationHistory=lead_data.get("ConversationHistory", ""),
        LINKEDIN=lead_data.get("LINKEDIN", "#"),
    )

    # Compose email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_email
    msg["To"] = notify_to
    if notify_cc:
        msg["Cc"] = notify_cc

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Build recipient list
    recipients = [notify_to]
    if notify_cc:
        recipients.extend([cc.strip() for cc in notify_cc.split(",") if cc.strip()])

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, recipients, msg.as_string())

        logger.info(f"✅ Email sent for lead: {name} ({country})")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "❌ SMTP authentication failed. Check SMTP_EMAIL and SMTP_PASSWORD. "
            "Make sure you're using a Gmail App Password, not your regular password."
        )
        return False
    except Exception as e:
        logger.error(f"❌ Failed to send email: {e}")
        return False
