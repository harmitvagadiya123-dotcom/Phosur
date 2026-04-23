import os
import json
import base64
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

def main():
    load_dotenv()
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64", "")
    spreadsheet_id = os.environ.get("BG001_SHEET_ID", "1bnz46ES2olQP7vPqvIpthBhF08TQ5RCN28ytcjjszsM")
    
    creds_json = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
    credentials = Credentials.from_service_account_info(creds_json, scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet("Gumloop_Blog_Creation")
    
    all_records = worksheet.get_all_records()
    print(f"Total records: {len(all_records)}")
    
    all_records = worksheet.get_all_records()
    row_2 = all_records[0] # Row 2 is index 0
    print("Full Record Details for Row 2:")
    for key, value in row_2.items():
        if key == "html":
            print(f"{key}: [HTML Content, {len(str(value))} characters]")
        else:
            print(f"{key}: {value}")

if __name__ == "__main__":
    main()
