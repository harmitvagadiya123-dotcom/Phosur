"""
gmail_service.py — Gmail IMAP reader + SMTP reply sender.

Replicates:
  - Gmail Trigger (poll unread, newer_than:1d)
  - Gmail8 (mark as read)
  - Gmail (reply with formatted HTML)
  - If2 (filter out own-domain / pathvancer emails)
"""
import os
import imaplib
import smtplib
import email
import logging
from email import encoders
from email.header import decode_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Max emails to process per run cycle (prevents runaway on large inboxes)
BATCH_LIMIT = 10

# Gmail label applied to every email that receives an automated reply
AUTORESPONDER_LABEL = "Autoresponder-Replied"

# ── Operation-specific labels (so you can filter by tag in Gmail) ──
TAG_KB_REPLY        = "OP/KB-Reply"          # KB match found → Agent 2 reply
TAG_FALLBACK_REPLY  = "OP/Fallback-Reply"    # No KB match → Agent 3 engagement reply
TAG_CLARIFICATION   = "OP/Clarification"     # More Info Needed → Agent 4 reply
TAG_SPAM_SKIPPED    = "OP/Spam-Skipped"      # Spam/Scam → skipped
TAG_NOT_INTERESTED  = "OP/Not-Interested"    # Not Interested → skipped
TAG_PENDING         = "OP/Pending"           # Ambiguous → skipped

# Addresses that should be skipped (own-domain filter, replicates If2 node)
SKIP_SENDERS = {"harmitvagadiya123@gmail.com", "pathvancer"}


def _get_credentials() -> tuple[str, str]:
    email_addr = os.environ.get("AUTORESPONDER_EMAIL", "").strip()
    password = os.environ.get("AUTORESPONDER_PASSWORD", "").strip()
    if not email_addr or not password:
        raise ValueError(
            "AUTORESPONDER_EMAIL and AUTORESPONDER_PASSWORD must be set in environment."
        )
    return email_addr, password


def _decode_header_value(value: str) -> str:
    """Decode encoded email header (RFC 2047)."""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_body(msg: email.message.Message) -> tuple[str, str]:
    """
    Extract plain text body and HTML body from an email message.
    Returns (plain_text, html_text).
    """
    plain = ""
    html = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain" and not plain:
                payload = part.get_payload(decode=True)
                if payload:
                    plain = payload.decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
            elif content_type == "text/html" and not html:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
            if msg.get_content_type() == "text/html":
                html = body
            else:
                plain = body

    return plain, html


def fetch_unread_emails() -> List[Dict]:
    """
    Connect to Gmail via IMAP, fetch unread emails from today.
    Returns a list of dicts with email metadata and body.
    Filters out own-domain / skip senders automatically.
    """
    email_addr, password = _get_credentials()

    emails = []
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_addr, password)
        mail.select("INBOX")

        # Search for unread emails (matches n8n filter: is:unread newer_than:1d)
        status, message_ids = mail.search(None, "UNSEEN")
        if status != "OK":
            logger.warning("⚠️ IMAP search returned non-OK status")
            return []

        ids = message_ids[0].split()
        # Take only the BATCH_LIMIT most recent unread emails
        ids = ids[-BATCH_LIMIT:]
        logger.info(f"📬 Found {len(message_ids[0].split())} unread, processing latest {len(ids)}")

        for msg_id in ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            sender_raw = msg.get("From", "")
            sender = _decode_header_value(sender_raw).lower()

            # Replicate n8n If2: filter out own-domain / skip senders
            skip = any(skip_kw.lower() in sender for skip_kw in SKIP_SENDERS)
            if skip:
                logger.info(f"⏭️ Skipping own-domain/internal email from: {sender}")
                continue

            subject = _decode_header_value(msg.get("Subject", "(No Subject)"))
            message_id_header = msg.get("Message-ID", "")
            in_reply_to = msg.get("In-Reply-To", "")
            references = msg.get("References", "")
            thread_id = in_reply_to or message_id_header
            to_addr = msg.get("To", "")
            date = msg.get("Date", "")

            plain_body, html_body = _get_body(msg)
            raw_body = html_body if html_body else plain_body

            # Get sender name and address
            sender_name = ""
            sender_email = ""
            if "<" in sender_raw:
                parts = sender_raw.split("<")
                sender_name = parts[0].strip().strip('"')
                sender_email = parts[1].strip().rstrip(">")
            else:
                sender_email = sender_raw.strip()

            emails.append(
                {
                    "imap_id": msg_id,
                    "message_id": message_id_header,
                    "thread_id": thread_id,
                    "in_reply_to": in_reply_to,
                    "references": references,
                    "subject": subject,
                    "from_name": sender_name,
                    "from_email": sender_email,
                    "to": to_addr,
                    "date": date,
                    "plain_body": plain_body,
                    "html_body": raw_body,
                }
            )

        mail.logout()

    except Exception as e:
        logger.error(f"❌ IMAP error: {e}", exc_info=True)

    return emails


def mark_as_read(imap_id: bytes) -> None:
    """Mark an email as read via IMAP (replicates Gmail8 node)."""
    try:
        email_addr, password = _get_credentials()
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_addr, password)
        mail.select("INBOX")
        mail.store(imap_id, "+FLAGS", "\\Seen")
        mail.logout()
        logger.info(f"✅ Marked email {imap_id} as read")
    except Exception as e:
        logger.error(f"❌ Failed to mark email as read: {e}")


def add_gmail_label(imap_id: bytes, label: str = AUTORESPONDER_LABEL) -> None:
    """
    Apply a Gmail label to an email via IMAP (Gmail IMAP extension X-GM-LABELS).
    Creates the label automatically if it doesn't exist.
    This is how n8n's 'Add label' Gmail nodes work.
    """
    try:
        email_addr, password = _get_credentials()
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_addr, password)
        mail.select("INBOX")

        # Gmail IMAP supports X-GM-LABELS for label management
        # The label name must be quoted if it contains spaces/special chars
        quoted_label = f'"{label}"' if " " in label else label
        result = mail.store(imap_id, "+X-GM-LABELS", quoted_label)

        if result[0] == "OK":
            logger.info(f"🏷️  Label '{label}' applied to email {imap_id}")
        else:
            logger.warning(f"⚠️ Could not apply label '{label}': {result}")

        mail.logout()
    except Exception as e:
        logger.error(f"❌ Failed to apply Gmail label: {e}")


def send_reply(
    to_email: str,
    subject: str,
    html_body: str,
    in_reply_to: str = "",
    references: str = "",
    imap_id: bytes = None,
    op_tag: str = "",
) -> bool:
    """
    Send an HTML reply email via Gmail SMTP.
    After sending, applies the 'Autoresponder-Replied' Gmail label
    plus an operation-specific tag (e.g. OP/KB-Reply) so you can
    identify all auto-replied emails and their processing path in Gmail.
    """
    try:
        from_email, password = _get_credentials()

        msg = MIMEMultipart("alternative")
        # Construct reply subject
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        msg["Subject"] = reply_subject
        msg["From"] = from_email
        msg["To"] = to_email

        # Thread headers for proper email threading
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        elif in_reply_to:
            msg["References"] = in_reply_to

        # Attach HTML body
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(from_email, password)
            server.sendmail(from_email, [to_email], msg.as_string())

        logger.info(f"✅ Reply sent to {to_email} | Subject: {reply_subject}")

        # ── Apply Gmail labels so the email is tagged in inbox ──
        if imap_id is not None:
            add_gmail_label(imap_id, AUTORESPONDER_LABEL)
            # Apply operation-specific tag
            if op_tag:
                add_gmail_label(imap_id, op_tag)
                logger.info(f"🏷️  OP tag applied: {op_tag}")

        return True

    except Exception as e:
        logger.error(f"❌ SMTP send failed: {e}", exc_info=True)
        return False


def tag_email(imap_id: bytes, op_tag: str) -> None:
    """
    Apply only an operation tag to an email (no reply sent).
    Used for emails that are skipped (Spam, Not Interested, Pending).
    """
    if imap_id is not None and op_tag:
        add_gmail_label(imap_id, op_tag)
        logger.info(f"🏷️  Skipped-email OP tag applied: {op_tag}")
