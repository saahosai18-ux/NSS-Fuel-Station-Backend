"""
NSS Fuel Station — FastAPI Backend
Main application entry point.

Run with: uvicorn app.main:app --reload --port 8000
Swagger docs: http://localhost:8000/docs
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.routers import auth, reports, inventory, credits, sync, users, ocr

app = FastAPI(
    title="NSS Fuel Station API",
    description="Backend API for NSS Fuel Station Management System",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow Flutter web app and local dev
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5000,http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins + ["*"],  # Allow all in dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(auth.router)
app.include_router(reports.router)
app.include_router(inventory.router)
app.include_router(credits.router)
app.include_router(sync.router)
app.include_router(users.router)
app.include_router(ocr.router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "app": "NSS Fuel Station API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    from app.services.supabase_service import get_supabase_client

    status = {"api": "ok", "supabase": "unknown"}

    try:
        supabase = get_supabase_client()
        result = supabase.table("pumps").select("id").limit(1).execute()
        status["supabase"] = "ok" if result.data is not None else "error"
    except Exception as e:
        status["supabase"] = f"error: {str(e)}"

    return status


# Startup event
@app.on_event("startup")
async def startup():
    print(">>> NSS Fuel Station API starting...")
    print(f"    Docs: http://localhost:8000/docs")
    print(f"    Supabase: {os.getenv('SUPABASE_URL', 'NOT SET')}")
