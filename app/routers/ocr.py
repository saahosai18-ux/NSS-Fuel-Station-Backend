from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional
from app.services.ocr_service import ocr_service
from app.services.supabase_service import get_current_user

router = APIRouter(prefix="/ocr", tags=["OCR"])

@router.post("/extract")
async def extract_ocr_data(
    file: UploadFile = File(...),
    type: str = Form("opening"),
    user: dict = Depends(get_current_user)
):
    """
    Extract data from a receipt image using Gemini OCR.
    """
    try:
        content = await file.read()
        data = await ocr_service.extract_receipt_data(content, type)
        
        if not data:
            raise HTTPException(status_code=500, detail="Failed to extract data from image")
            
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
