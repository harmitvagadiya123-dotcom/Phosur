"""
session_service.py — Google Sheets session management for the Packaging Chatbot.

Manages sessions in the Google Sheet:
  Spreadsheet: 1erIY6nUrWBzPimCmnvZk6IAFg-mBOwykB9nW8juTDto
  Sheet tab:   Session_Information_packaging

Columns: id | conversation_history | context_data | created_at | last_activity
"""

import os
import json
import base64
import logging
from datetime import datetime
from typing import Optional, Dict

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# Google API scopes
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SESSION_SHEET_NAME = "Session_Information_packaging"
CUSTOMER_SHEET_NAME = "ChatbotCustomerInformation_Pacaging"


def _get_client() -> gspread.Client:
    """Create an authenticated gspread client from env credentials."""
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


def lookup_session(session_id: str) -> Optional[Dict]:
    """
    Look up a session by ID in the Session_Information_packaging sheet.
    Returns the row data dict if found, None if not found.
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(_get_sheet_id())
        worksheet = spreadsheet.worksheet(SESSION_SHEET_NAME)
        all_records = worksheet.get_all_records()

        for record in all_records:
            if str(record.get("id", "")).strip() == str(session_id).strip():
                logger.info(f"✅ Session found: {session_id}")
                return record

        logger.info(f"📭 Session not found: {session_id}")
        return None

    except Exception as e:
        logger.error(f"❌ Session lookup failed: {e}", exc_info=True)
        return None


def create_session(session_id: str, first_message: str) -> bool:
    """
    Create a new session row in the Session_Information_packaging sheet.
    Columns: id, conversation_history, context_data, created_at, last_activity
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(_get_sheet_id())
        worksheet = spreadsheet.worksheet(SESSION_SHEET_NAME)

        now = datetime.utcnow().isoformat() + "Z"
        row = [session_id, first_message, "", now, now]
        worksheet.append_row(row, value_input_option="USER_ENTERED")

        logger.info(f"✅ New session created: {session_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to create session: {e}", exc_info=True)
        return False


def update_session_history(
    session_id: str,
    user_message: str,
    bot_response: str,
) -> bool:
    """
    Update conversation_history and context_data for an existing session.
    Appends to existing values with comma separation (matching n8n behavior).
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(_get_sheet_id())
        worksheet = spreadsheet.worksheet(SESSION_SHEET_NAME)

        # Find the row
        all_records = worksheet.get_all_records()
        row_index = None
        for idx, record in enumerate(all_records):
            if str(record.get("id", "")).strip() == str(session_id).strip():
                row_index = idx + 2  # 1-indexed + header row
                existing_history = str(record.get("conversation_history", ""))
                existing_context = str(record.get("context_data", ""))
                break

        if row_index is None:
            logger.warning(f"⚠️ Session {session_id} not found for update")
            return False

        # Append to conversation history and context
        new_history = f"{existing_history},{user_message}" if existing_history else user_message
        new_context = f"{existing_context},{bot_response}" if existing_context else bot_response
        now = datetime.utcnow().isoformat() + "Z"

        # Update columns: B=conversation_history, C=context_data, E=last_activity
        worksheet.update_cell(row_index, 2, new_history)
        worksheet.update_cell(row_index, 3, new_context)
        worksheet.update_cell(row_index, 5, now)

        logger.info(f"✅ Session history updated: {session_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to update session history: {e}", exc_info=True)
        return False
