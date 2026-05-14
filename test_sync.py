import asyncio
import json
from app.services.sheets_service import sync_all_on_approval

report_data = {
  "id": "6b647f9b-decf-4625-93a4-804c14a75254",
  "dsm_id": "181ac3cd-199f-4ac2-bde2-30376f185ef1",
  "pump_id": "1",
  "shift": "day",
  "date": "2026-05-02",
  "open_n1": 1,
  "open_n2": 1,
  "open_n3": 1,
  "open_n4": 1,
  "close_n1": 1,
  "close_n2": 1,
  "close_n3": 1,
  "close_n4": 2,
  "hsd_sold": 0,
  "ms_sold": 1,
  "hsd_net": 0,
  "ms_net": 1,
  "hsd_price": 91.29,
  "ms_price": 103.24,
  "hsd_sales": 0,
  "ms_sales": 103.24,
  "total_sales": 103.24,
  "expected_sales": 103.24,
  "cash": 103,
  "upi": 0,
  "pine": 0,
  "otp": 0,
  "card": 0,
  "credit_total": 0,
  "gross_collected": 103,
  "expenses": 0,
  "testing_amt": 0,
  "bp_rewards": 0,
  "net_collected": 103,
  "variance": 0.24,
  "variance_status": "PERFECT",
  "cash_in_hand": 103,
  "open_hsd": 0,
  "load_hsd": 0,
  "test_hsd": 0,
  "close_hsd": 0,
  "open_ms": 0,
  "load_ms": 0,
  "test_ms": 0,
  "close_ms": -1,
  "dsm_name": "ba",
  "manager_name": "bab",
  "pump_name": "Pump 1"
}

async def main():
    result = await sync_all_on_approval(report_data, [])
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
