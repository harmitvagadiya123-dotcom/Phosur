"""
buying_intent_detector.py — Detects buying intent from user messages.

Replicates the "Buying_intent" n8n Code node.
Uses keyword-based matching to classify intent as high / medium / low.
Also updates the customer info sheet with buying intent data.
"""

import os
import re
import json
import base64
import logging
from typing import Dict

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CUSTOMER_SHEET_NAME = "ChatbotCustomerInformation_Pacaging"

# 🔴 HIGH INTENT — Ready to buy
HIGH_INTENT_WORDS = [
    'buy', 'purchase', 'order', 'how much', 'price', 'cost',
    'checkout', 'payment', 'urgent', 'asap', 'need now',
    'kitne ka', 'lena hai', 'buy now', 'place order',
]

# 🟡 MEDIUM INTENT — Interested
MEDIUM_INTENT_WORDS = [
    'interested', 'available', 'stock', 'dm me',
    'link', 'website', 'delivery', 'shipping', 'webinar',
    'join', 'fees', 'milega', 'kaha milega',
    'how to order', 'where to buy',
]


def detect_buying_intent(message: str) -> Dict:
    """
    Detect buying intent from a message using keyword matching.
    Returns: {"has_buying_intent": bool, "intent_level": str, "high_matches": int, "medium_matches": int}
    """
    if not message or not message.strip():
        return {
            "has_buying_intent": False,
            "intent_level": "none",
            "high_matches": 0,
            "medium_matches": 0,
        }

    text = message.lower()

    high_matches = sum(1 for word in HIGH_INTENT_WORDS if word in text)
    medium_matches = sum(1 for word in MEDIUM_INTENT_WORDS if word in text)

    if high_matches >= 1:
        intent_level = "high"
        has_buying_intent = True
    elif medium_matches >= 1:
        intent_level = "medium"
        has_buying_intent = True
    else:
        intent_level = "low"
        has_buying_intent = False

    logger.info(f"🎯 Intent: {intent_level}, Buying: {has_buying_intent} (high={high_matches}, medium={medium_matches})")

    return {
        "has_buying_intent": has_buying_intent,
        "intent_level": intent_level,
        "high_matches": high_matches,
        "medium_matches": medium_matches,
    }


def _get_client() -> gspread.Client:
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64", "")
    if not creds_b64:
        raise ValueError("GOOGLE_CREDENTIALS_BASE64 env var is not set")
    creds_json = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
    credentials = Credentials.from_service_account_info(creds_json, scopes=_SCOPES)
    return gspread.authorize(credentials)


def _get_sheet_id() -> str:
    return os.environ.get(
        "PACKAGING_SHEET_ID",
        "1erIY6nUrWBzPimCmnvZk6IAFg-mBOwykB9nW8juTDto",
    )


def update_buying_intent_sheet(
    session_id: str,
    intent_level: str,
    conversation_history: str,
) -> bool:
    """
    Update the buying intent columns in the ChatbotCustomerInformation_Pacaging sheet.
    Columns: buying Intent (col 6), buying intent message (col 7)
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(_get_sheet_id())
        worksheet = spreadsheet.worksheet(CUSTOMER_SHEET_NAME)

        all_records = worksheet.get_all_records()
        row_index = None
        for idx, record in enumerate(all_records):
            if str(record.get("id", "")).strip() == str(session_id).strip():
                row_index = idx + 2
                break

        if row_index is None:
            logger.warning(f"⚠️ Session {session_id} not found in customer sheet for intent update")
            return False

        worksheet.update_cell(row_index, 6, intent_level)
        worksheet.update_cell(row_index, 7, conversation_history)

        logger.info(f"✅ Buying intent updated for {session_id}: {intent_level}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to update buying intent: {e}", exc_info=True)
        return False
