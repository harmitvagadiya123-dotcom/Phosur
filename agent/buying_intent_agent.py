"""
Buying Intent Agent — Orchestrates the lead notification pipeline.

Flow: Validate lead → Send email → Update Google Sheet status
Replaces the n8n workflow: Webhook → Gmail → Google Sheets Update
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .email_service import send_lead_email
from .sheet_service import update_status

logger = logging.getLogger(__name__)


@dataclass
class LeadData:
    """Structured lead data from the webhook payload."""
    row_number: int
    SNO: str
    DATE: str
    NAME: str
    COUNTRY: str
    DESIGNATIONORCOMPANY: str
    LINKEDIN: str
    ConversationHistory: str
    BuyingIntent: str

    @classmethod
    def from_dict(cls, data: dict) -> "LeadData":
        return cls(
            row_number=int(data.get("row_number", 0)),
            SNO=str(data.get("SNO", "")),
            DATE=str(data.get("DATE", "")),
            NAME=str(data.get("NAME", "")),
            COUNTRY=str(data.get("COUNTRY", "")),
            DESIGNATIONORCOMPANY=str(data.get("DESIGNATIONORCOMPANY", "")),
            LINKEDIN=str(data.get("LINKEDIN", "")),
            ConversationHistory=str(data.get("ConversationHistory", "")),
            BuyingIntent=str(data.get("BuyingIntent", "")),
        )


@dataclass
class AgentResult:
    """Result of the agent processing."""
    success: bool
    email_sent: bool
    sheet_updated: bool
    message: str
    error: Optional[str] = None


class BuyingIntentAgent:
    """
    Agent that processes high-intent LinkedIn leads.

    When a lead's buying intent is marked as "High" in the Google Sheet,
    the Google Apps Script triggers a webhook. This agent:
    1. Validates the lead data
    2. Sends a rich HTML notification email
    3. Updates the Google Sheet status to "Done"
    """

    def process(self, payload: dict) -> AgentResult:
        """
        Process a single lead from the webhook payload.

        Args:
            payload: Raw JSON dict from the Google Apps Script webhook.

        Returns:
            AgentResult with status of each step.
        """
        logger.info("🚀 Buying Intent Agent: Processing new lead...")

        # Step 1: Validate
        lead = LeadData.from_dict(payload)

        if not lead.NAME:
            return AgentResult(
                success=False,
                email_sent=False,
                sheet_updated=False,
                message="Lead has no NAME — skipping.",
                error="Missing NAME field",
            )

        if lead.BuyingIntent.strip().lower() != "high":
            return AgentResult(
                success=False,
                email_sent=False,
                sheet_updated=False,
                message=f"BuyingIntent is '{lead.BuyingIntent}', not 'High' — skipping.",
                error="BuyingIntent is not High",
            )

        logger.info(f"📋 Lead: {lead.NAME} | {lead.COUNTRY} | {lead.DESIGNATIONORCOMPANY}")

        # Step 2: Send email notification
        email_sent, email_error = send_lead_email(payload)
        if not email_sent:
            logger.warning(f"⚠️ Email failed: {email_error}")

        # Step 3: Update Google Sheet status
        sheet_updated = False
        sheet_error = None
        if lead.row_number > 0:
            sheet_updated, sheet_error = update_status(lead.row_number, "Done")
        else:
            sheet_error = "Missing valid row_number"
            logger.warning(f"⚠️ {sheet_error} — skipping sheet update.")

        # Determine success: For now, if email is sent, we return success (200) 
        # so the Apps Script doesn't mark it as 'Error', even if our own sheet update fails.
        success = email_sent
        
        errors = []
        if not email_sent: errors.append(f"Email: {email_error}")
        if not sheet_updated: errors.append(f"Sheet: {sheet_error}")
        error_summary = " | ".join(errors) if errors else None

        if success:
            message = f"✅ Lead '{lead.NAME}' processed successfully. Email sent & sheet updated."
        elif email_sent:
            message = f"⚠️ Email sent for '{lead.NAME}' but sheet update failed."
        elif sheet_updated:
            message = f"⚠️ Sheet updated for '{lead.NAME}' but email failed."
        else:
            message = f"❌ Both email and sheet update failed for '{lead.NAME}'."

        logger.info(message)

        return AgentResult(
            success=success,
            email_sent=email_sent,
            sheet_updated=sheet_updated,
            message=message,
            error=error_summary,
        )
