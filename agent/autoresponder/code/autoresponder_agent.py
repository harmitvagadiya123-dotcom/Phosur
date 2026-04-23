"""
autoresponder_agent.py — Main orchestrator for the Autoresponder Support agent.

Replicates the full n8n 'Autoresponder Support- Phosur' workflow in Python.

Pipeline:
  1. Poll Gmail for unread emails (IMAP)
  2. Mark as read immediately
  3. Filter own-domain senders
  4. Classify: Spam / Scam / Valid (AI Agent 6)
  5. Strip HTML → cleanedContent
  6. Classify intent: Ready to Send / More Info Needed / Not Interested / Pending
  7. Route by category:
     - Ready to Send Data:
         → Search Supabase KB (documents 2)
         → If match: format reply from KB answer (Agent 2)
         → If no match: generate engagement reply (Agent 3)
         → Send reply
     - More Info Needed:
         → Search KB for context
         → Generate clarification reply (Agent 4)
         → Send reply
     - Not Interested / Pending:
         → Log and skip
"""
import logging
import time

from .html_utils import strip_html
from .gmail_service import (
    fetch_unread_emails, mark_as_read, send_reply, tag_email,
    TAG_KB_REPLY, TAG_FALLBACK_REPLY, TAG_CLARIFICATION,
    TAG_SPAM_SKIPPED, TAG_NOT_INTERESTED, TAG_PENDING,
)
from .spam_classifier import classify_email
from .intent_classifier import classify_intent
from .kb_search import search_knowledge_base
from .email_formatter import (
    format_kb_reply,
    format_fallback_reply,
    format_clarification_reply,
)

logger = logging.getLogger(__name__)


class AutoresponderAgent:
    """
    Autoresponder Support Agent for Phosur / Shubh Packaging.
    Polls Gmail, classifies emails, searches KB, and sends professional replies.
    """

    def run(self) -> dict:
        """
        Execute one full cycle of the autoresponder pipeline.
        Returns a summary dict of what happened.
        """
        logger.info("=" * 60)
        logger.info("🚀 Autoresponder Agent — Starting run")
        logger.info("=" * 60)

        summary = {
            "emails_found": 0,
            "spam_skipped": 0,
            "not_interested_skipped": 0,
            "pending_skipped": 0,
            "replies_sent": 0,
            "errors": 0,
        }

        # ── Step 1: Fetch unread emails ──────────────────────────
        emails = fetch_unread_emails()
        summary["emails_found"] = len(emails)

        if not emails:
            logger.info("📭 No new unread emails. Done.")
            return summary

        for email_data in emails:
            try:
                self._process_email(email_data, summary)
            except Exception as e:
                logger.error(
                    f"💥 Unhandled error processing email '{email_data.get('subject', '?')}': {e}",
                    exc_info=True,
                )
                summary["errors"] += 1

            # Small delay between emails to avoid rate limiting
            time.sleep(2)

        logger.info("=" * 60)
        logger.info(f"✅ Autoresponder run complete: {summary}")
        logger.info("=" * 60)
        return summary

    def _process_email(self, email_data: dict, summary: dict) -> None:
        imap_id = email_data["imap_id"]
        subject = email_data.get("subject", "(No Subject)")
        from_email = email_data.get("from_email", "")
        from_name = email_data.get("from_name", "")
        in_reply_to = email_data.get("in_reply_to", "")
        references = email_data.get("references", "")
        message_id = email_data.get("message_id", "")
        html_body = email_data.get("html_body", "")
        plain_body = email_data.get("plain_body", "")

        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"📧 Processing email:")
        logger.info(f"   From    : {from_name} <{from_email}>")
        logger.info(f"   Subject : {subject}")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ── Step 2: Mark as read immediately ────────────────────
        mark_as_read(imap_id)

        raw_content = html_body or plain_body

        # ── Step 3: Spam / Scam / Valid classification ───────────
        validity = classify_email(raw_content, subject, from_email)
        logger.info(f"🔍 Email validity: {validity}")

        if validity != "Valid":
            logger.info(f"⏭️  Skipping {validity} email: {subject[:60]}")
            summary["spam_skipped"] += 1
            tag_email(imap_id, TAG_SPAM_SKIPPED)
            return

        # ── Step 4: Strip HTML → cleanedContent ─────────────────
        cleaned_content = strip_html(raw_content)
        if not cleaned_content:
            cleaned_content = plain_body.strip()
        logger.info(f"📝 Cleaned content ({len(cleaned_content)} chars)")

        # ── Step 5: Intent classification ───────────────────────
        intent_result = classify_intent(cleaned_content)
        category = intent_result.get("category", "Pending")
        logger.info(f"🏷️  Intent: {category}")

        # ── Step 6: Route by category ───────────────────────────
        if category == "Ready to Send Data":
            self._handle_ready(
                email_data["imap_id"], from_email, from_name, subject, cleaned_content,
                in_reply_to, references or message_id, summary
            )

        elif category == "More Info Needed":
            self._handle_more_info(
                email_data["imap_id"], from_email, from_name, subject, cleaned_content,
                in_reply_to, references or message_id, summary
            )

        elif category == "Not Interested":
            logger.info("⏭️  Not Interested — no reply sent")
            summary["not_interested_skipped"] += 1
            tag_email(imap_id, TAG_NOT_INTERESTED)

        else:  # Pending
            logger.info("⏳ Pending — no reply sent")
            summary["pending_skipped"] += 1
            tag_email(imap_id, TAG_PENDING)

    # ── Route handlers ─────────────────────────────────────────────

    def _handle_ready(
        self,
        imap_id: bytes,
        to_email: str,
        sender_name: str,
        subject: str,
        cleaned_content: str,
        in_reply_to: str,
        references: str,
        summary: dict,
    ) -> None:
        """
        Handle 'Ready to Send Data' emails.
        Search KB → if found use Agent 2, else use Agent 3.
        """
        logger.info("📦 Category: Ready to Send Data — searching KB...")
        kb_result = search_knowledge_base(cleaned_content, top_k=10)

        if kb_result["data_found"] and kb_result["matched_rows"]:
            # Use best match answer (AI Agent 2)
            best_answer = kb_result["matched_rows"][0]["answer"]
            logger.info(f"✅ KB match found (similarity={kb_result['matched_rows'][0]['similarity']})")
            html_reply = format_kb_reply(subject, best_answer, sender_name)
            op_tag = TAG_KB_REPLY
        else:
            # Generate engagement reply (AI Agent 3)
            logger.info("📭 No KB match — generating fallback reply (Agent 3)")
            html_reply = format_fallback_reply(subject, cleaned_content, sender_name)
            op_tag = TAG_FALLBACK_REPLY

        sent = send_reply(to_email, subject, html_reply, in_reply_to, references, imap_id=imap_id, op_tag=op_tag)
        if sent:
            summary["replies_sent"] += 1
        else:
            summary["errors"] += 1

    def _handle_more_info(
        self,
        imap_id: bytes,
        to_email: str,
        sender_name: str,
        subject: str,
        cleaned_content: str,
        in_reply_to: str,
        references: str,
        summary: dict,
    ) -> None:
        """
        Handle 'More Info Needed' emails.
        Search KB for context → generate clarification reply (AI Agent 4).
        """
        logger.info("🔄 Category: More Info Needed — generating clarification reply...")
        kb_result = search_knowledge_base(cleaned_content, top_k=3)
        kb_rows = kb_result.get("matched_rows", [])

        html_reply = format_clarification_reply(subject, cleaned_content, sender_name, kb_rows)

        sent = send_reply(to_email, subject, html_reply, in_reply_to, references, imap_id=imap_id, op_tag=TAG_CLARIFICATION)
        if sent:
            summary["replies_sent"] += 1
        else:
            summary["errors"] += 1
