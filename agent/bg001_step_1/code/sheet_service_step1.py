import os
import logging
import json
import base64
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# Scopes for Google Sheets and Drive
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

class SheetServiceStep1:
    """Service to handle sheet operations for BG001 Step 1."""
    
    def __init__(self, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.client = _get_client()
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)

    def get_due_rss_feeds(self, sheet_name: str = "Gumloop_Blog_Creation_input") -> List[Dict]:
        """
        Reads rows where status is 'inprogress' and Date is due.
        """
        worksheet = self.spreadsheet.worksheet(sheet_name)
        all_records = worksheet.get_all_records()
        
        due_feeds = []
        now = datetime.now()

        for idx, row in enumerate(all_records):
            status = str(row.get("status", "")).strip().lower()
            date_str = str(row.get("Date", "")).strip()
            
            # 1-indexed row number
            row_number = idx + 2 

            if status == "inprogress":
                is_due = False
                if not date_str:
                    is_due = True
                else:
                    try:
                        # Assuming dd-MM-yyyy based on n8n workflow
                        due_date = datetime.strptime(date_str, "%d-%m-%Y")
                        if due_date <= now:
                            is_due = True
                    except ValueError:
                        logger.warning(f"⚠️ Invalid date format at row {row_number}: {date_str}")
                        is_due = True # Process if format is broken?

                if is_due:
                    row["row_number"] = row_number
                    due_feeds.append(row)

        logger.info(f"📋 Found {len(due_feeds)} due feeds.")
        return due_feeds

    def update_next_run_date(self, row_number: int, days_ahead: int = 10, sheet_name: str = "Gumloop_Blog_Creation_input"):
        """Updates the Date column (Column C / index 3) with today + 10 days."""
        worksheet = self.spreadsheet.worksheet(sheet_name)
        next_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%d-%m-%Y")
        worksheet.update_cell(row_number, 3, next_date)
        logger.info(f"✅ Updated row {row_number} next run date to {next_date}")

    def add_to_tracking_sheet(self, url: str, sheet_name: str = "Gumloop_Blog_Creation"):
        """
        Adds a URL to the tracking sheet with status 'InProgress'.
        Avoids duplicates if simple.
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            # Simple deduplication: check if URL exists in column A
            urls = worksheet.col_values(1)
            if url in urls:
                logger.info(f"⏭️ URL already exists in tracking sheet: {url}")
                return

            # Append: url, status
            worksheet.append_row([url, "InProgress"])
            logger.info(f"✅ Added to tracking sheet: {url}")
        except Exception as e:
            logger.error(f"❌ Failed to add to tracking sheet: {e}")

