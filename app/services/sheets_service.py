"""
Google Sheets API v4 service — sync data via service account.
Called when Manager approves a report.
Updates 3 sheets atomically: FUEL SALES, CREDIT LEDGER, INVENTORY.
"""
import os
from typing import List, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_service = None


def _get_service():
    """Get or create the Google Sheets API service."""
    global _service
    if _service is not None:
        return _service

    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"Google credentials not found at {GOOGLE_CREDENTIALS_PATH}. "
            "Download from GCP Console → Service Account → Keys."
        )

    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
    )
    _service = build("sheets", "v4", credentials=credentials)
    return _service


def append_to_sheet(sheet_name: str, values: List[List]) -> dict:
    """
    Append rows to a specific sheet tab.

    Args:
        sheet_name: Tab name (e.g., "FUEL SALES", "CREDIT LEDGER", "INVENTORY")
        values: List of rows, each row is a list of cell values

    Returns:
        Google Sheets API response
    """
    if not GOOGLE_SHEETS_ID:
        raise ValueError(
            "GOOGLE_SHEETS_ID not set. Copy the ID from your Google Sheets URL."
        )

    service = _get_service()
    body = {"values": values}

    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range=f"{sheet_name}!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
    )
    return result


def sync_fuel_sales(report: dict) -> dict:
    """
    Append a fuel sales row to the FUEL SALES sheet.

    Columns: Date, Pump, Shift, DSM, HSD Litres, MS Litres,
             HSD Sales, MS Sales, Total Sales, Cash, UPI, Pine,
             OTP, Credit, Expenses, Variance, Status
    """
    row = [
        report.get("date", ""),
        report.get("pump_name", ""),
        report.get("shift", "day"),
        report.get("dsm_name", ""),
        report.get("hsd_net", 0),
        report.get("ms_net", 0),
        report.get("hsd_sales", 0),
        report.get("ms_sales", 0),
        report.get("total_sales", 0),
        report.get("cash", 0),
        report.get("upi", 0),
        report.get("pine", 0),
        report.get("otp", 0),
        report.get("credit_total", 0),
        report.get("expenses", 0),
        report.get("variance", 0),
        report.get("variance_status", ""),
    ]
    return append_to_sheet("FUEL SALES", [row])


def sync_credit_ledger(entries: List[dict]) -> dict:
    """
    Append credit entries to the CREDIT LEDGER sheet.

    Columns: Date, Customer, Amount Given, Amount Received, Balance,
             Fuel Type, Litres, Note
    """
    rows = []
    for entry in entries:
        balance = entry.get("amount", 0) - entry.get("amount_received", 0)
        rows.append([
            entry.get("date", ""),
            entry.get("customer_name", ""),
            entry.get("amount", 0),
            entry.get("amount_received", 0),
            balance,
            entry.get("fuel_type", ""),
            entry.get("litres", 0),
            entry.get("note", ""),
        ])
    if rows:
        return append_to_sheet("CREDIT LEDGER", rows)
    return {"status": "no_entries"}


def sync_inventory(report: dict) -> dict:
    """
    Append inventory data to the INVENTORY sheet.

    Columns: Date, Fuel Type, Opening Stock, Received, Sold, Testing,
             Closing Stock
    """
    rows = []
    # HSD row
    rows.append([
        report.get("date", ""),
        "HSD",
        report.get("open_hsd", 0),
        report.get("load_hsd", 0),
        report.get("hsd_net", 0),
        report.get("test_hsd", 0),
        report.get("close_hsd", 0),
    ])
    # MS row
    rows.append([
        report.get("date", ""),
        "MS",
        report.get("open_ms", 0),
        report.get("load_ms", 0),
        report.get("ms_net", 0),
        report.get("test_ms", 0),
        report.get("close_ms", 0),
    ])
    return append_to_sheet("INVENTORY", rows)


async def sync_all_on_approval(report: dict, credit_entries: List[dict]) -> dict:
    """
    Sync all 3 sheets atomically when a report is approved.
    Called from the reports router when manager approves.

    Returns results from all 3 syncs.
    """
    results = {}
    errors = []

    try:
        results["fuel_sales"] = sync_fuel_sales(report)
    except Exception as e:
        errors.append(f"FUEL SALES sync failed: {e}")

    try:
        results["credit_ledger"] = sync_credit_ledger(credit_entries)
    except Exception as e:
        errors.append(f"CREDIT LEDGER sync failed: {e}")

    try:
        results["inventory"] = sync_inventory(report)
    except Exception as e:
        errors.append(f"INVENTORY sync failed: {e}")

    if errors:
        results["errors"] = errors
        results["synced"] = False
    else:
        results["synced"] = True

    return results


def ensure_sheet_headers():
    """
    Ensure all 3 sheet tabs have header rows.
    Call once during setup.
    """
    headers = {
        "FUEL SALES": [
            ["Date", "Pump", "Shift", "DSM", "HSD Litres", "MS Litres",
             "HSD Sales", "MS Sales", "Total Sales", "Cash", "UPI", "Pine",
             "OTP", "Credit", "Expenses", "Variance", "Status"]
        ],
        "CREDIT LEDGER": [
            ["Date", "Customer", "Amount Given", "Amount Received", "Balance",
             "Fuel Type", "Litres", "Note"]
        ],
        "INVENTORY": [
            ["Date", "Fuel Type", "Opening Stock", "Received", "Sold",
             "Testing", "Closing Stock"]
        ],
    }

    for sheet_name, header_rows in headers.items():
        try:
            service = _get_service()
            # Check if sheet already has data
            result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=GOOGLE_SHEETS_ID,
                    range=f"{sheet_name}!A1:A1",
                )
                .execute()
            )
            if not result.get("values"):
                append_to_sheet(sheet_name, header_rows)
        except Exception:
            # Sheet might not exist yet, try appending anyway
            try:
                append_to_sheet(sheet_name, header_rows)
            except Exception:
                pass
