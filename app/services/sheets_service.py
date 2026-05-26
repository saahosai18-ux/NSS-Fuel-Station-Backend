"""
Google Sheets API v4 service — sync data via service account.
Called when Manager approves a report.
Updates 6 sheets atomically: DAILY SALES, NOZZLE READINGS, COLLECTION, INVENTORY, CREDIT LEDGER, EXPENSES.
"""
import os
from typing import List, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_service = None

def _get_service():
    """Get or create the Google Sheets API service."""
    global _service
    if _service is not None:
        return _service

    import json
    
    if GOOGLE_CREDENTIALS_JSON:
        try:
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
        except Exception as e:
            raise ValueError(f"Failed to parse GOOGLE_CREDENTIALS_JSON: {e}")
    else:
        if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
            raise FileNotFoundError(
                f"Google credentials not found at {GOOGLE_CREDENTIALS_PATH}. "
                "Download from GCP Console → Service Account → Keys or set GOOGLE_CREDENTIALS_JSON."
            )

        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
        )
        
    _service = build("sheets", "v4", credentials=credentials)
    return _service

def append_to_sheet(sheet_name: str, values: List[List]) -> dict:
    if not GOOGLE_SHEETS_ID:
        raise ValueError("GOOGLE_SHEETS_ID not set.")
    service = _get_service()
    body = {"values": values}
    return service.spreadsheets().values().append(
        spreadsheetId=GOOGLE_SHEETS_ID,
        range=f"'{sheet_name}'!A:Z",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()

def sync_daily_sales(report: dict) -> dict:
    # DAILY SALES: Date, Pump, Serial No, DSM Name, Manager, Shift Start, Shift End, HSD Sold, MS Sold, Total Litres, HSD Rate, MS Rate, HSD Sales, MS Sales, Testing Deduction, NET SALES, Status, Difference, Approved At
    row = [
        report.get("date", ""),
        report.get("pump_name", ""),
        str(report.get("id", ""))[:6], # Serial No
        report.get("dsm_name", ""),
        report.get("manager_name", ""),
        report.get("shift", ""), # Shift Start
        "", # Shift End (Placeholder for future)
        report.get("hsd_net", 0),
        report.get("ms_net", 0),
        float(report.get("hsd_net", 0)) + float(report.get("ms_net", 0)),
        report.get("hsd_price", 0),
        report.get("ms_price", 0),
        report.get("hsd_sales", 0),
        report.get("ms_sales", 0),
        report.get("testing_amt", 0),
        report.get("total_sales", 0),
        report.get("variance_status", ""),
        report.get("variance", 0),
        report.get("approved_at", "")
    ]
    return append_to_sheet("DAILY SALES", [row])

def sync_nozzle_readings(report: dict) -> dict:
    # NOZZLE READINGS: Date, Pump, Serial No, N1 Open, N1 Close, N1 Sold, N2... N3... N4..., Total HSD, Total MS
    n1_sold = float(report.get("close_n1", 0)) - float(report.get("open_n1", 0))
    n2_sold = float(report.get("close_n2", 0)) - float(report.get("open_n2", 0))
    n3_sold = float(report.get("close_n3", 0)) - float(report.get("open_n3", 0))
    n4_sold = float(report.get("close_n4", 0)) - float(report.get("open_n4", 0))
    row = [
        report.get("date", ""),
        report.get("pump_name", ""),
        str(report.get("id", ""))[:6],
        report.get("open_n1", 0), report.get("close_n1", 0), n1_sold,
        report.get("open_n2", 0), report.get("close_n2", 0), n2_sold,
        report.get("open_n3", 0), report.get("close_n3", 0), n3_sold,
        report.get("open_n4", 0), report.get("close_n4", 0), n4_sold,
        report.get("hsd_sold", 0), # Total HSD from meter
        report.get("ms_sold", 0), # Total MS from meter
    ]
    return append_to_sheet("NOZZLE READINGS", [row])

def sync_collection(report: dict) -> dict:
    # COLLECTION: Date, Pump, Serial No, Cash, UPI, Pine Labs, OTP, Credit Given, Gross Collected, Expenses Paid, BP Rewards, CASH IN HAND
    row = [
        report.get("date", ""),
        report.get("pump_name", ""),
        str(report.get("id", ""))[:6],
        report.get("cash", 0),
        report.get("upi", 0),
        report.get("pine", 0),
        report.get("otp", 0),
        report.get("credit_total", 0),
        report.get("gross_collected", 0),
        report.get("expenses", 0),
        report.get("bp_rewards", 0),
        report.get("cash_in_hand", 0)
    ]
    return append_to_sheet("COLLECTION", [row])

def sync_inventory(report: dict) -> dict:
    # INVENTORY: Date, Pump, Serial No, HSD Open, HSD Load, HSD Sold, HSD Test, HSD Close, MS Open, MS Load, MS Sold, MS Test, MS Close
    row = [
        report.get("date", ""),
        report.get("pump_name", ""),
        str(report.get("id", ""))[:6],
        report.get("open_hsd", 0),
        report.get("load_hsd", 0),
        report.get("hsd_net", 0),
        report.get("test_hsd", 0),
        report.get("close_hsd", 0),
        report.get("open_ms", 0),
        report.get("load_ms", 0),
        report.get("ms_net", 0),
        report.get("test_ms", 0),
        report.get("close_ms", 0)
    ]
    return append_to_sheet("INVENTORY", [row])

# sync_credit_ledger removed because ledger part is removed

def sync_expenses(report: dict) -> dict:
    # EXPENSES: Date, Pump, Serial No, Description, Amount
    if float(report.get("expenses", 0)) > 0:
        expense_entries = report.get("expense_entries", [])
        if expense_entries:
            rows = []
            for entry in expense_entries:
                rows.append([
                    report.get("date", ""),
                    report.get("pump_name", ""),
                    str(report.get("id", ""))[:6],
                    entry.get("description", "Shift Expense"),
                    entry.get("amount", 0)
                ])
            return append_to_sheet("EXPENSES", rows)
        else:
            row = [
                report.get("date", ""),
                report.get("pump_name", ""),
                str(report.get("id", ""))[:6],
                "Shift Expense",
                report.get("expenses", 0)
            ]
            return append_to_sheet("EXPENSES", [row])
    return {"status": "no_expenses"}

async def sync_all_on_approval(report: dict, credit_entries: List[dict]) -> dict:
    results = {}
    errors = []

    try:
        results["daily_sales"] = sync_daily_sales(report)
    except Exception as e:
        errors.append(f"DAILY SALES sync failed: {e}")

    try:
        results["nozzle_readings"] = sync_nozzle_readings(report)
    except Exception as e:
        errors.append(f"NOZZLE READINGS sync failed: {e}")

    try:
        results["collection"] = sync_collection(report)
    except Exception as e:
        errors.append(f"COLLECTION sync failed: {e}")

    try:
        results["inventory"] = sync_inventory(report)
    except Exception as e:
        errors.append(f"INVENTORY sync failed: {e}")

    # credit_ledger sync removed because ledger part is removed

    try:
        results["expenses"] = sync_expenses(report)
    except Exception as e:
        errors.append(f"EXPENSES sync failed: {e}")

    if errors:
        results["errors"] = errors
        results["synced"] = False
    else:
        results["synced"] = True

    return results

def get_dashboard_data() -> dict:
    """
    Reads the 'DASHBOARD' tab to get the 'TODAY SUMMARY'.
    Extracts the grid data.
    """
    if not GOOGLE_SHEETS_ID:
        raise ValueError("GOOGLE_SHEETS_ID not set.")
    
    service = _get_service()
    
    result = service.spreadsheets().values().get(
        spreadsheetId=GOOGLE_SHEETS_ID,
        range="'DASHBOARD'!A1:Z30"
    ).execute()
    
    values = result.get('values', [])
    return {"values": values}

