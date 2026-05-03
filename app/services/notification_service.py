"""
Notification service — Firebase Cloud Messaging (FCM) for push notifications.
Sends notifications when DSM submits a report → Manager gets notified.
This is OPTIONAL — the app works without it.
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Firebase is optional — gracefully degrade if not configured
_firebase_initialized = False

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")

    if FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        print("[OK] Firebase initialized for push notifications")
    else:
        print("[INFO] Firebase credentials not found - push notifications disabled")
except ImportError:
    print("[INFO] firebase-admin not installed - push notifications disabled")
except Exception as e:
    print(f"[WARN] Firebase init error: {e}")


async def send_notification(
    topic: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> dict:
    """
    Send a push notification via FCM.

    Args:
        topic: FCM topic (e.g., "managers" — all managers subscribe)
        title: Notification title
        body: Notification body text
        data: Optional data payload

    Returns:
        {"sent": bool, "message_id": str or error}
    """
    if not _firebase_initialized:
        return {"sent": False, "reason": "Firebase not configured"}

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            topic=topic,
        )
        response = messaging.send(message)
        return {"sent": True, "message_id": response}
    except Exception as e:
        return {"sent": False, "error": str(e)}


async def notify_report_submitted(
    dsm_name: str,
    pump_name: str,
    report_date: str,
):
    """Notify managers when a DSM submits a report."""
    return await send_notification(
        topic="managers",
        title="📋 New Report Submitted",
        body=f"{dsm_name} submitted {pump_name} report for {report_date}",
        data={
            "type": "report_submitted",
            "dsm_name": dsm_name,
            "pump_name": pump_name,
            "date": report_date,
        },
    )


async def notify_report_approved(
    pump_name: str,
    report_date: str,
    dsm_id: str,
):
    """Notify DSM when their report is approved."""
    return await send_notification(
        topic=f"user_{dsm_id}",
        title="✅ Report Approved",
        body=f"Your {pump_name} report for {report_date} has been approved",
        data={
            "type": "report_approved",
            "pump_name": pump_name,
            "date": report_date,
        },
    )


async def notify_report_rejected(
    pump_name: str,
    report_date: str,
    dsm_id: str,
    reason: str,
):
    """Notify DSM when their report is rejected."""
    return await send_notification(
        topic=f"user_{dsm_id}",
        title="❌ Report Rejected",
        body=f"Your {pump_name} report was rejected: {reason}",
        data={
            "type": "report_rejected",
            "pump_name": pump_name,
            "date": report_date,
            "reason": reason,
        },
    )


async def notify_low_stock(fuel_type: str, current_stock: float, threshold: float):
    """Notify managers and owner about low stock."""
    return await send_notification(
        topic="managers",
        title=f"⚠️ Low {fuel_type} Stock Alert",
        body=f"{fuel_type} stock at {current_stock:.0f}L — below threshold of {threshold:.0f}L",
        data={
            "type": "low_stock",
            "fuel_type": fuel_type,
            "current_stock": str(current_stock),
            "threshold": str(threshold),
        },
    )
