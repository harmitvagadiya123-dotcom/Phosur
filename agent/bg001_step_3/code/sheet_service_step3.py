import os
import logging
import json
import base64
from typing import List, Dict, Optional

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


def _get_col_index(headers: list, col_name: str) -> Optional[int]:
    """Find 1-indexed column number by header name (case-insensitive)."""
    for i, h in enumerate(headers):
        if str(h).strip().lower() == col_name.strip().lower():
            return i + 1  # gspread uses 1-indexed columns
    return None


class SheetServiceStep3:
    """Service to handle sheet operations for BG001 Step 3 (WordPress publishing)."""

    def __init__(self, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.client = _get_client()
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)

    def get_approved_row(self, sheet_name: str = "Gumloop_Blog_Creation") -> Optional[Dict]:
        """
        Reads the FIRST row where status='complete' AND publish status='Approved'.
        Returns None if no matching row is found.
        """
        worksheet = self.spreadsheet.worksheet(sheet_name)
        all_records = worksheet.get_all_records()

        # Log all headers for debugging
        headers = worksheet.row_values(1)
        logger.info(f"📊 Sheet headers: {headers}")
        logger.info(f"📊 Total rows (excluding header): {len(all_records)}")

        for idx, row in enumerate(all_records):
            status = str(row.get("status", "")).strip().lower()
            publish_status = str(row.get("publish status", "")).strip().lower()

            if status == "complete" and publish_status == "approved":
                row["row_number"] = idx + 2  # 1-indexed, skip header
                # Log full record details
                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                logger.info(f"📋 MATCHED ROW {row['row_number']}:")
                for key, value in row.items():
                    if key == "html":
                        logger.info(f"   {key}: [{len(str(value))} chars]")
                    else:
                        logger.info(f"   {key}: {value}")
                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                return row

        logger.info("📊 No rows matched filters: status='complete' AND publish status='Approved'")
        return None

    def _get_worksheet_and_columns(self, sheet_name: str):
        """Get worksheet and a map of column names to 1-indexed positions."""
        worksheet = self.spreadsheet.worksheet(sheet_name)
        headers = worksheet.row_values(1)
        col_map = {}
        for i, h in enumerate(headers):
            col_map[str(h).strip().lower()] = i + 1
        logger.info(f"📊 Column map: {col_map}")
        return worksheet, col_map

    def update_row_published(
        self,
        row_number: int,
        wp_title: str,
        wp_slug: str,
        sheet_name: str = "Gumloop_Blog_Creation",
    ):
        """
        Marks a row as 'Published' and updates the title/slug from the WP response.
        Uses dynamic column lookup from header row.
        """
        worksheet, col_map = self._get_worksheet_and_columns(sheet_name)

        # Update status
        status_col = col_map.get("status")
        if status_col:
            worksheet.update_cell(row_number, status_col, "Published")
            logger.info(f"✅ Row {row_number}, col {status_col} (status) → 'Published'")
        else:
            logger.error(f"❌ 'status' column not found in headers!")

        # Update title
        title_col = col_map.get("title")
        if title_col and wp_title:
            worksheet.update_cell(row_number, title_col, wp_title)
            logger.info(f"✅ Row {row_number}, col {title_col} (title) → '{wp_title[:50]}'")

        # Update slug
        slug_col = col_map.get("slug")
        if slug_col and wp_slug:
            worksheet.update_cell(row_number, slug_col, wp_slug)
            logger.info(f"✅ Row {row_number}, col {slug_col} (slug) → '{wp_slug}'")

        logger.info(f"✅ Row {row_number} fully marked as Published")

    def update_row_errored(
        self,
        row_number: int,
        sheet_name: str = "Gumloop_Blog_Creation",
    ):
        """
        Marks a row as 'Errored' when validation fails (missing title or feature image).
        Uses dynamic column lookup from header row.
        """
        worksheet, col_map = self._get_worksheet_and_columns(sheet_name)

        status_col = col_map.get("status")
        if status_col:
            worksheet.update_cell(row_number, status_col, "Errored")
            logger.info(f"⚠️ Row {row_number}, col {status_col} (status) → 'Errored'")
        else:
            logger.error(f"❌ 'status' column not found in headers!")

        logger.warning(f"⚠️ Row {row_number} marked as Errored (validation failed)")
