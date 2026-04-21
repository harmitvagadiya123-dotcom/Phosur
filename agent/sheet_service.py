"""
Google Sheets Service — Updates lead status in the Buying Intent sheet.

Uses gspread + google-auth with Service Account credentials.
Credentials are provided as a base64-encoded JSON env var.
"""

import os
import json
import base64
import logging

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# Google Sheets API scopes
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_client() -> gspread.Client:
    """Create an authenticated gspread client from env credentials."""
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64", "")
    if not creds_b64:
        raise ValueError("GOOGLE_CREDENTIALS_BASE64 env var is not set")

    creds_json = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
    credentials = Credentials.from_service_account_info(creds_json, scopes=_SCOPES)
    return gspread.authorize(credentials)


from typing import Tuple, Optional

def update_status(row_number: int, status: str = "Done") -> Tuple[bool, Optional[str]]:
    """
    Update the Status_Sent column (Column I, index 9) for a given row.

    Args:
        row_number: The 1-indexed row number in the sheet.
        status: The status value to set (default: "Done").

    Returns:
        (True, None) if update succeeded.
        (False, error_msg) otherwise.
    """
    sheet_id = os.environ.get(
        "GOOGLE_SHEET_ID", "1W1wWwvc3t6Z7WOHAocI5hSQuz2bFTSDPMqgeZ0T_QHE"
    )
    sheet_name = os.environ.get("GOOGLE_SHEET_NAME", "Buying_intent_Linkedin")

    try:
        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        # Column I = column 9 (Status_Sent)
        worksheet.update_cell(row_number, 9, status)

        logger.info(f"✅ Sheet updated: Row {row_number} → Status_Sent = '{status}'")
        return True, None

    except Exception as e:
        err = f"Sheet update failed: {str(e)}"
        logger.error(f"❌ {err}")
        return False, err
