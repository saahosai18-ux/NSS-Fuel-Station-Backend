"""
Users router — endpoints for Managers to list, approve, deactivate, and delete profiles.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional

from app.services.supabase_service import (
    get_supabase_admin, get_current_user, require_role, log_audit
)

router = APIRouter(prefix="/users", tags=["User Management"])


class ProfileResponse(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    role: str
    is_approved: bool
    is_active: bool
    created_at: str

class UpdateUserStatusRequest(BaseModel):
    action: str  # "approve", "deactivate", "activate", "delete"


@router.get("/", response_model=List[ProfileResponse])
async def list_users(user: dict = Depends(require_role("manager", "owner"))):
    """List all profiles (DSMs and Managers)."""
    supabase = get_supabase_admin()
    
    # We fetch profiles
    profiles_res = supabase.table("profiles").select("*").order("created_at", desc=True).execute()
    profiles = profiles_res.data or []

    # Try to fetch emails from auth.users (requires service role)
    user_email_map = {}
    try:
        auth_users = supabase.auth.admin.list_users()
        for u in auth_users:
            user_email_map[u.id] = u.email
    except Exception as e:
        print(f"Error fetching auth users: {e}")
    
    result = []
    for p in profiles:
        email_val = user_email_map.get(p["id"], p.get("phone", ""))
        result.append({
            "id": p["id"],
            "name": p["name"],
            "role": p["role"],
            "is_approved": p.get("is_approved", False),
            "is_active": p.get("is_active", True),
            "created_at": p["created_at"],
            "email": email_val
        })
        
    return result


@router.put("/{target_user_id}/status")
async def update_user_status(
    target_user_id: str,
    body: UpdateUserStatusRequest,
    user: dict = Depends(require_role("manager", "owner")),
):
    """
    Approve, deactivate, activate, or delete a user.
    """
    supabase = get_supabase_admin()
    
    # Fetch target user profile
    res = supabase.table("profiles").select("*").eq("id", target_user_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User not found")
        
    target_profile = res.data

    # Owners can manage managers and DSMs. Managers can only manage DSMs.
    if user["role"] == "manager" and target_profile["role"] in ["manager", "owner"]:
         raise HTTPException(status_code=403, detail="Managers cannot modify other managers or owners")

    action = body.action.lower()
    
    if action == "approve":
        update_data = {"is_approved": True, "is_active": True}
        supabase.table("profiles").update(update_data).eq("id", target_user_id).execute()
        await log_audit(user["id"], "approve_user", "profiles", target_user_id)
        return {"status": "success", "message": "User approved successfully"}

    elif action == "deactivate":
        update_data = {"is_active": False}
        supabase.table("profiles").update(update_data).eq("id", target_user_id).execute()
        await log_audit(user["id"], "deactivate_user", "profiles", target_user_id)
        return {"status": "success", "message": "User deactivated"}

    elif action == "activate":
        update_data = {"is_active": True, "is_approved": True}
        supabase.table("profiles").update(update_data).eq("id", target_user_id).execute()
        await log_audit(user["id"], "activate_user", "profiles", target_user_id)
        return {"status": "success", "message": "User activated"}

    elif action == "delete":
        # Delete from profiles (auth.users delete might cascade)
        # Note: True deletion from auth.users requires admin API `supabase.auth.admin.delete_user(id)`
        try:
            supabase.auth.admin.delete_user(target_user_id)
            await log_audit(user["id"], "delete_user", "profiles", target_user_id)
            return {"status": "success", "message": "User permanently deleted"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")

    else:
        raise HTTPException(status_code=400, detail="Invalid action")


