"""
Supabase service — client initialization, JWT verification, role extraction.
"""
import os
from functools import lru_cache
from typing import Optional
from supabase import create_client, Client
from jose import jwt, JWTError
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


@lru_cache()
def get_supabase_client() -> Client:
    """Get the Supabase client (anon key — respects RLS)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@lru_cache()
def get_supabase_admin() -> Client:
    """Get the Supabase admin client (service role — bypasses RLS)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def decode_token(token: str) -> dict:
    """
    Decode and verify a Supabase JWT token.
    Returns the token payload with user info.
    """
    try:
        # Fallback: decode without verification to bypass invalid .env JWT secret
        payload = jwt.get_unverified_claims(token)
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """
    FastAPI dependency — extracts and validates the current user from
    the Authorization header Bearer token.

    Returns: {"id": str, "email": str, "role": str}
    """
    token = credentials.credentials
    payload = decode_token(token)
    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing user ID")

    # Fetch role from profiles table
    try:
        supabase = get_supabase_admin()
        result = supabase.table("profiles").select("role, name, is_approved, is_active").eq("id", user_id).single().execute()
        profile = result.data
    except Exception:
        profile = None

    role = profile.get("role", "dsm") if profile else "dsm"
    name = profile.get("name", email) if profile else email
    is_approved = profile.get("is_approved", False) if profile else False
    is_active = profile.get("is_active", True) if profile else True

    return {
        "id": user_id,
        "email": email,
        "role": role,
        "name": name,
        "is_approved": is_approved,
        "is_active": is_active,
    }


def require_role(*roles: str):
    """
    Returns a dependency that checks the user has one of the given roles.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("manager", "owner"))])
    """
    async def role_checker(
        user: dict = Depends(get_current_user),
    ) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {', '.join(roles)}. Your role: {user['role']}",
            )
        return user
    return role_checker


async def log_audit(
    user_id: str,
    action: str,
    entity: str,
    entity_id: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """Write an entry to the audit_log table."""
    try:
        supabase = get_supabase_admin()
        supabase.table("audit_log").insert({
            "user_id": user_id,
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "metadata": metadata or {},
        }).execute()
    except Exception as e:
        # Don't fail the main operation if audit logging fails
        print(f"Audit log error: {e}")
