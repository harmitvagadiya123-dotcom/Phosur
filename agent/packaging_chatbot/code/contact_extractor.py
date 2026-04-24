"""
contact_extractor.py — Extracts company/contact details from user messages.

Replicates two n8n nodes:
  - "Extract Company Details1" (regex-based detection)
  - "Code in JavaScript1" (detailed extraction)
  - "AI Agent" (LLM-based structured extraction of name/website/email/phone)
  - "Save to Google Sheet1" (save to ChatbotCustomerInformation_Pacaging)
"""

import os
import re
import json
import base64
import logging
from typing import Dict, Optional

import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CUSTOMER_SHEET_NAME = "ChatbotCustomerInformation_Pacaging"


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


def has_company_details(message: str) -> bool:
    """
    Check if the message contains company/contact details (website, email, phone).
    Replicates the "Extract Company Details1" n8n Code node regex logic.
    """
    # Website pattern
    website_pattern = r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})(?:/[^\s]*)?'
    # Email pattern
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    # Phone pattern (10-15 digit numbers, with optional formatting)
    phone_pattern = r'(?:\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}|\(\d{3}\)\s?\d{3}[-.\s]?\d{4}|\d{3}[-.\s]\d{3}[-.\s]\d{4}|\b\d{10,15}\b)'

    has_website = bool(re.search(website_pattern, message, re.IGNORECASE))
    has_email = bool(re.search(email_pattern, message, re.IGNORECASE))
    has_phone = bool(re.search(phone_pattern, message))

    result = has_website or has_email or has_phone
    logger.info(f"🔍 Company details check: website={has_website}, email={has_email}, phone={has_phone} → {result}")
    return result


def extract_contact_details_regex(message: str) -> Dict:
    """
    Regex-based extraction of contact info from the message.
    Replicates the "Code in JavaScript1" n8n node.
    """
    extracted = {
        "name": None,
        "email": None,
        "phone": None,
        "website": None,
    }

    # Email
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
    if email_match:
        extracted["email"] = email_match.group(0)

    # Phone
    phone_patterns = [
        r'\+?\d{1,4}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
        r'\(\d{3}\)\s?\d{3}[-.\s]?\d{4}',
        r'\d{3}[-.\s]\d{3}[-.\s]\d{4}',
        r'\d{10,}',
    ]
    for pattern in phone_patterns:
        match = re.search(pattern, message)
        if match:
            phone = match.group(0).strip()
            digits = re.sub(r'\D', '', phone)
            if 10 <= len(digits) <= 15:
                extracted["phone"] = phone
                break

    # Website / URL
    url_patterns = [
        r'https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_+.~#?&/=]*',
        r'www\.[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_+.~#?&/=]*',
        r'\b[-a-zA-Z0-9@:%._+~#=]{1,256}\.(?:com|org|net|co|io|ai|app|dev|tech|uk|us|in|ca|au)\b',
    ]
    for pattern in url_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            website = match.group(0).strip()
            if not website.startswith(('http://', 'https://')):
                website = 'https://' + website
            extracted["website"] = website
            break

    # Name extraction heuristics
    name_patterns = [
        r"(?:my\s+name\s+is|i(?:'m|\s+am)|this\s+is|call\s+me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"(?:name)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)(?:\s+(?:here|speaking|calling))",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match and match.group(1):
            extracted["name"] = match.group(1).strip()
            break

    # Fallback: capitalized word sequences
    if not extracted["name"]:
        cap_matches = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', message)
        if cap_matches:
            common_words = {'Hello', 'Hi', 'My', 'Please', 'Thank', 'Thanks', 'The'}
            filtered = [w for w in cap_matches if w not in common_words]
            if filtered:
                extracted["name"] = filtered[0]

    return extracted


def extract_contact_details_ai(message: str, regex_data: Dict) -> Dict:
    """
    Use AI (OpenRouter LLM) to extract structured contact info.
    Replicates the "AI Agent" node with Structured Output Parser.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("⚠️ OPENROUTER_API_KEY not set, using regex results only")
        return regex_data

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    system_prompt = """You are a specialized data extraction assistant. Your sole purpose is to extract contact information from user messages and return it in a structured JSON format.

EXTRACTION RULES:
1. Extract the following fields: name, website, phone and email
2. If any field is not found, set it to blank
3. Be intelligent about context
4. ALWAYS return valid JSON only - no explanations, no markdown

Return ONLY this JSON, nothing else:
{
  "name": "extracted name",
  "website": "extracted website",
  "phone": "extracted phone",
  "email": "extracted email"
}"""

    user_prompt = f"""Extract name, website, email and phone from this message. Return JSON only:
input message: {message}

Context : {json.dumps(regex_data)}
also extracted values can be found from context"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        logger.info(f"✅ AI extraction result: {result}")
        return result

    except Exception as e:
        logger.error(f"❌ AI contact extraction failed: {e}", exc_info=True)
        return regex_data


def save_customer_info(session_id: str, contact_data: Dict) -> bool:
    """
    Save/update customer information in the ChatbotCustomerInformation_Pacaging sheet.
    Columns: id | name | website | email_address | contact_number | buying Intent | buying intent message
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(_get_sheet_id())
        worksheet = spreadsheet.worksheet(CUSTOMER_SHEET_NAME)

        # Check if session_id already exists
        all_records = worksheet.get_all_records()
        row_index = None
        for idx, record in enumerate(all_records):
            if str(record.get("id", "")).strip() == str(session_id).strip():
                row_index = idx + 2
                break

        name = contact_data.get("name", "") or ""
        website = contact_data.get("website", "") or ""
        email = contact_data.get("email", "") or ""
        phone = contact_data.get("phone", "") or ""

        if row_index:
            # Update existing row
            worksheet.update_cell(row_index, 2, name)
            worksheet.update_cell(row_index, 3, website)
            worksheet.update_cell(row_index, 4, email)
            worksheet.update_cell(row_index, 5, phone)
            logger.info(f"✅ Updated customer info for session {session_id}")
        else:
            # Append new row: id, name, website, email_address, contact_number
            row = [session_id, name, website, email, phone, "", ""]
            worksheet.append_row(row, value_input_option="USER_ENTERED")
            logger.info(f"✅ Created customer info for session {session_id}")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to save customer info: {e}", exc_info=True)
        return False
