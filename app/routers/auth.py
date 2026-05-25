"""
Auth router — login, signup, and current user endpoints.
Proxies to Supabase Auth.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
import random
from datetime import datetime, timedelta, timezone
from app.services.supabase_service import (
    get_supabase_client,
    get_supabase_admin,
    get_current_user,
    log_audit,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)
    role: str = Field(default="dsm", pattern="^(dsm|manager|owner)$")
    phone: Optional[str] = None
    manager_id: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str
    role: str
    name: str
    is_approved: bool = False
    is_active: bool = True


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Login with email and password.
    Returns JWT access token and user profile.
    """
    try:
        supabase = get_supabase_client()
        result = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
        })

        user = result.user
        session = result.session

        if not user or not session:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Fetch profile to get role and status
        admin = get_supabase_admin()
        profile_result = admin.table("profiles").select("*").eq("id", user.id).single().execute()
        profile = profile_result.data

        # Explicitly check for deactivated users
        if profile and profile.get("is_active") is False:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        return AuthResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user_id=user.id,
            email=user.email,
            role=profile.get("role", "dsm") if profile else "dsm",
            name=profile.get("name", user.email) if profile else user.email,
            is_approved=profile.get("is_approved", False) if profile else False,
            is_active=profile.get("is_active", True) if profile else True,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")


@router.get("/managers")
async def get_managers():
    """Get a list of all active managers and owners for DSM assignment."""
    try:
        admin = get_supabase_admin()
        res = admin.table("profiles").select("id, name, role").eq("is_active", True).in_("role", ["manager", "owner"]).execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch managers: {str(e)}")


class VerifyOtpRequest(BaseModel):
    email: str
    otp: str


@router.post("/verify-otp")
async def verify_otp(request: VerifyOtpRequest):
    """
    Verify DSM's signup OTP.
    If valid, approves the profile, clears OTP fields.
    """
    try:
        admin = get_supabase_admin()
        
        # Look up auth user by email
        users_result = admin.auth.admin.list_users()
        target_user = None
        for u in users_result:
            if u.email.lower() == request.email.lower():
                target_user = u
                break
                
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found with this email")
            
        profile_res = admin.table("profiles").select("*").eq("id", target_user.id).single().execute()
        profile = profile_res.data
        if not profile:
            raise HTTPException(status_code=404, detail="User profile not found")
            
        otp_code = profile.get("signup_otp_code")
        expires_at_str = profile.get("signup_otp_expires_at")
        
        if not otp_code or not expires_at_str:
            raise HTTPException(status_code=400, detail="No active registration OTP found for this account")
            
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        
        if now > expires_at:
            raise HTTPException(status_code=400, detail="OTP has expired. Please sign up again to get a new code.")
            
        if otp_code != request.otp.strip():
            raise HTTPException(status_code=400, detail="Invalid OTP code")
            
        # Approve user and clear OTP fields
        admin.table("profiles").update({
            "is_approved": True,
            "signup_otp_code": None,
            "signup_otp_expires_at": None
        }).eq("id", target_user.id).execute()
        
        await log_audit(target_user.id, "verify_signup_otp", "profiles", target_user.id)
        
        return {"status": "success", "message": "Account approved successfully. Please login."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OTP verification failed: {str(e)}")


@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """
    Register a new user with email, password, name, role, phone, and manager.
    The profile is auto-created via database trigger and then updated here.
    """
    try:
        supabase = get_supabase_client()
        result = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {
                    "name": request.name,
                    "role": request.role,
                }
            }
        })

        user = result.user
        session = result.session

        if not user:
            raise HTTPException(status_code=400, detail="Signup failed")

        # Now, update the profile table to set manager_id, phone, and OTP if they are a DSM
        admin = get_supabase_admin()
        
        # Managers and owners start approved. DSMs must verify via OTP.
        is_approved = request.role in ["manager", "owner"]
        
        update_data = {
            "phone": request.phone,
            "is_approved": is_approved
        }
        
        otp_val = None
        assigned_manager_id = None
        if request.role == "dsm":
            assigned_manager_id = request.manager_id
            
            # If no manager_id was selected, find the first active manager/owner
            if not assigned_manager_id:
                mgrs_res = admin.table("profiles").select("id").eq("is_active", True).in_("role", ["manager", "owner"]).limit(1).execute()
                if mgrs_res.data:
                    assigned_manager_id = mgrs_res.data[0]["id"]
            
            if assigned_manager_id:
                update_data["manager_id"] = assigned_manager_id
                
                # Generate 6-digit OTP code
                otp_val = f"{random.randint(100000, 999999)}"
                update_data["signup_otp_code"] = otp_val
                update_data["signup_otp_expires_at"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
            else:
                # If there are absolutely no managers in the system, allow them to register approved so they aren't blocked
                update_data["is_approved"] = True
        
        # Perform the update on profiles
        admin.table("profiles").update(update_data).eq("id", user.id).execute()
        
        # If OTP was generated, create the notification for the manager
        if otp_val and assigned_manager_id:
            admin.table("notifications").insert({
                "user_id": assigned_manager_id,
                "title": "🔑 New DSM Registration",
                "body": f"DSM {request.name} is registering. Share this OTP: {otp_val}",
                "data": {
                    "type": "dsm_signup_otp",
                    "dsm_id": user.id,
                    "dsm_name": request.name,
                    "otp": otp_val
                }
            }).execute()

        # Fetch the updated profile to return exact details
        profile_res = admin.table("profiles").select("is_approved, is_active").eq("id", user.id).single().execute()
        updated_profile = profile_res.data
        
        current_is_approved = updated_profile.get("is_approved", False) if updated_profile else is_approved
        current_is_active = updated_profile.get("is_active", True) if updated_profile else True

        if session:
            return AuthResponse(
                access_token=session.access_token,
                refresh_token=session.refresh_token,
                user_id=user.id,
                email=user.email,
                role=request.role,
                name=request.name,
                is_approved=current_is_approved,
                is_active=current_is_active,
            )
        else:
            return AuthResponse(
                access_token="",
                refresh_token="",
                user_id=user.id,
                email=user.email or request.email,
                role=request.role,
                name=request.name,
                is_approved=current_is_approved,
                is_active=current_is_active,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Signup failed: {str(e)}")


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get the current authenticated user's profile."""
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "is_approved": user.get("is_approved", False),
        "is_active": user.get("is_active", True),
    }


@router.post("/refresh")
async def refresh_token(refresh_token: str):
    """Refresh the JWT access token."""
    try:
        supabase = get_supabase_client()
        result = supabase.auth.refresh_session(refresh_token)
        session = result.session

        if not session:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Refresh failed: {str(e)}")
