"""
Auth router — login, signup, and current user endpoints.
Proxies to Supabase Auth.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from app.services.supabase_service import (
    get_supabase_client,
    get_supabase_admin,
    get_current_user,
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


@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """
    Register a new user with email, password, name, and role.
    The profile is auto-created via database trigger.
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

        # If email confirmation is disabled, session is available immediately
        if session:
            return AuthResponse(
                access_token=session.access_token,
                refresh_token=session.refresh_token,
                user_id=user.id,
                email=user.email,
                role=request.role,
                name=request.name,
                is_approved=False, # Newly signed up users are never approved by default
                is_active=True,
            )
        else:
            # Email confirmation is enabled — return partial response
            return AuthResponse(
                access_token="",
                refresh_token="",
                user_id=user.id,
                email=user.email or request.email,
                role=request.role,
                name=request.name,
                is_approved=False,
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
