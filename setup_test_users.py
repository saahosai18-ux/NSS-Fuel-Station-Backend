"""
Setup script — creates test users, pumps, and fuel prices for testing.
Run once: python setup_test_users.py
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load keys from .env
load_dotenv()

url = os.environ.get("SUPABASE_URL")
# We must use the SERVICE_ROLE_KEY to bypass RLS and create users directly
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") 

supabase: Client = create_client(url, key)

def setup():
    print(">>> Starting Full Setup...\n")
    
    # ── 1. Create Manager ──
    print("--- Creating Manager (manager@nss.com)...")
    try:
        res = supabase.auth.admin.create_user({
            "email": "manager@nss.com",
            "password": "password123",
            "email_confirm": True
        })
        manager_id = res.user.id
        
        supabase.table("profiles").upsert({
            "id": manager_id,
            "role": "manager",
            "name": "Priya Manager",
            "is_approved": True,
            "is_active": True,
        }).execute()
        print(f"[OK] Manager created! ID: {manager_id}")
    except Exception as e:
        if "already been registered" in str(e) or "already exists" in str(e):
            print("[SKIP] Manager already exists — ensuring profile is approved...")
            # Find existing user and ensure approved
            users = supabase.auth.admin.list_users()
            for u in users:
                if u.email == "manager@nss.com":
                    supabase.table("profiles").upsert({
                        "id": u.id,
                        "role": "manager",
                        "name": "Priya Manager",
                        "is_approved": True,
                        "is_active": True,
                    }).execute()
                    print(f"[OK] Manager profile updated! ID: {u.id}")
                    break
        else:
            print(f"[ERROR] Could not create Manager: {e}")

    # ── 2. Create DSM ──
    print("\n--- Creating DSM (raju@nss.com)...")
    try:
        res = supabase.auth.admin.create_user({
            "email": "raju@nss.com",
            "password": "password123",
            "email_confirm": True
        })
        dsm_id = res.user.id
        
        supabase.table("profiles").upsert({
            "id": dsm_id,
            "role": "dsm",
            "name": "Raju Kumar",
            "is_approved": True,
            "is_active": True,
        }).execute()
        print(f"[OK] DSM created! ID: {dsm_id}")
    except Exception as e:
        if "already been registered" in str(e) or "already exists" in str(e):
            print("[SKIP] DSM already exists — ensuring profile is approved...")
            users = supabase.auth.admin.list_users()
            for u in users:
                if u.email == "raju@nss.com":
                    supabase.table("profiles").upsert({
                        "id": u.id,
                        "role": "dsm",
                        "name": "Raju Kumar",
                        "is_approved": True,
                        "is_active": True,
                    }).execute()
                    print(f"[OK] DSM profile updated! ID: {u.id}")
                    break
        else:
            print(f"[ERROR] Could not create DSM: {e}")

    # ── 3. Verify Pumps exist ──
    print("\n--- Checking pumps...")
    try:
        result = supabase.table("pumps").select("id, name, display_name").execute()
        if result.data:
            print(f"[OK] Found {len(result.data)} pumps:")
            for p in result.data:
                print(f"     {p['display_name']} (id: {p['id'][:8]}...)")
        else:
            print("[WARN] No pumps found! Seeding...")
            supabase.table("pumps").insert([
                {"name": "P1", "display_name": "Pump 1", "fuel_type": "HSD"},
                {"name": "P2", "display_name": "Pump 2", "fuel_type": "HSD"},
                {"name": "P3", "display_name": "Pump 3", "fuel_type": "MS"},
            ]).execute()
            print("[OK] 3 pumps seeded.")
    except Exception as e:
        print(f"[ERROR] Pump check failed: {e}")

    # ── 4. Verify Fuel Prices exist ──
    print("\n--- Checking fuel prices...")
    try:
        result = supabase.table("fuel_prices").select("fuel_type, price_per_litre").execute()
        if result.data:
            for p in result.data:
                print(f"     {p['fuel_type']}: INR {p['price_per_litre']}/L")
        else:
            print("[WARN] No fuel prices! Seeding...")
            supabase.table("fuel_prices").insert([
                {"fuel_type": "HSD", "price_per_litre": 91.29, "margin_per_litre": 2.50},
                {"fuel_type": "MS", "price_per_litre": 103.24, "margin_per_litre": 3.00},
            ]).execute()
            print("[OK] Fuel prices seeded.")
    except Exception as e:
        print(f"[ERROR] Fuel prices check failed: {e}")

    # ── 5. Verify Inventory exists ──
    print("\n--- Checking inventory...")
    try:
        result = supabase.table("inventory").select("fuel_type, opening_stock").execute()
        if result.data:
            for i in result.data:
                print(f"     {i['fuel_type']}: {i['opening_stock']}L opening")
        else:
            print("[WARN] No inventory! Seeding...")
            supabase.table("inventory").insert([
                {"fuel_type": "HSD", "opening_stock": 5000, "closing_stock": 5000, "threshold": 500},
                {"fuel_type": "MS", "opening_stock": 3000, "closing_stock": 3000, "threshold": 500},
            ]).execute()
            print("[OK] Inventory seeded.")
    except Exception as e:
        print(f"[ERROR] Inventory check failed: {e}")

    print("\n" + "="*50)
    print("SETUP COMPLETE!")
    print("="*50)
    print("\nTest credentials:")
    print("  DSM:     raju@nss.com     / password123")
    print("  Manager: manager@nss.com  / password123")
    print("\nNext steps:")
    print("  1. Run backend:  uvicorn app.main:app --reload --host 0.0.0.0")
    print("  2. Run Flutter:  flutter run")
    print("  3. Login as DSM → submit report → logout → login as Manager → approve")

if __name__ == "__main__":
    setup()
