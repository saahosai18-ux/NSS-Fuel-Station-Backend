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
    role: str = Field(default="manager", pattern="^(manager|owner)$")
    phone: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str
    role: str
    name: str
    is_approved: bool = True
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
        profile = None
        try:
            profile_result = admin.table("profiles").select("*").eq("id", user.id).single().execute()
            profile = profile_result.data
        except Exception as e:
            error_str = str(e)
            if "PGRST116" in error_str or "0 rows" in error_str or "single JSON object" in error_str:
                # Profile is missing (e.g. database wipe). Auto-create it.
                role = "dsm"
                email_lower = user.email.lower()
                if "manager" in email_lower or "mgr" in email_lower:
                    role = "manager"
                elif "owner" in email_lower:
                    role = "owner"
                
                # Check seed emails
                if email_lower == "manager@nss.com":
                    role = "manager"
                elif email_lower == "owner@nss.com":
                    role = "owner"
                elif email_lower == "raju@nss.com":
                    role = "dsm"

                try:
                    insert_res = admin.table("profiles").insert({
                        "id": user.id,
                        "email": user.email,
                        "role": role,
                        "name": user.email.split("@")[0],
                        "is_approved": True,
                        "is_active": True
                    }).execute()
                    if insert_res.data:
                        profile = insert_res.data[0]
                except Exception as insert_err:
                    print(f"Failed to auto-create profile on login: {insert_err}")
            else:
                raise e

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


@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """
    Register a new manager/owner with email, password, name, and role.
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

        admin = get_supabase_admin()
        
        # Managers/owners are auto-approved
        update_data = {
            "phone": request.phone,
            "is_approved": True,
            "is_active": True
        }
        
        # Perform the update on profiles
        admin.table("profiles").update(update_data).eq("id", user.id).execute()
        
        if session:
            return AuthResponse(
                access_token=session.access_token,
                refresh_token=session.refresh_token,
                user_id=user.id,
                email=user.email,
                role=request.role,
                name=request.name,
                is_approved=True,
                is_active=True,
            )
        else:
            return AuthResponse(
                access_token="",
                refresh_token="",
                user_id=user.id,
                email=user.email or request.email,
                role=request.role,
                name=request.name,
                is_approved=True,
                is_active=True,
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
