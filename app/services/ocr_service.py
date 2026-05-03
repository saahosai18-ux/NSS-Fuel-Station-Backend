import os
import json
import base64
import google.generativeai as genai
from typing import Optional, Dict, Any

class OCRService:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-flash-latest')

    async def extract_receipt_data(self, image_bytes: bytes, receipt_type: str = "opening") -> Optional[Dict[str, Any]]:
        """
        Extracts Vtot readings and timestamp from a receipt image using Gemini 1.5 Flash.
        """
        prompt = f"""
        You are an expert OCR system for a fuel station management app. 
        Analyze this image of a {receipt_type} shift receipt or pump meter reading.
        
        Extract the following fields accurately:
        1. N1 HSD VTOT (Number)
        2. N2 HSD VTOT (Number)
        3. N3 MS VTOT (Number)
        4. N4 MS VTOT (Number)
        5. Receipt Date (Format: YYYY-MM-DD)
        6. Receipt Time (Format: HH:MM AM/PM)

        Important Rules:
        - Return ONLY a valid JSON object.
        - If a value is missing or unreadable, use null.
        - The Vtot values are cumulative readings usually labeled as "VTOT" or "TOTALIZER".
        - There are typically 4 nozzles (N1, N2 are HSD; N3, N4 are MS/Petrol).
        
        Output Format:
        {{
            "n1_hsd_vtot": float,
            "n2_hsd_vtot": float,
            "n3_ms_vtot": float,
            "n4_ms_vtot": float,
            "receipt_date": "YYYY-MM-DD",
            "receipt_time": "HH:MM AM/PM"
        }}
        """

        try:
            # Prepare image for Gemini
            image_parts = [
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            ]

            response = self.model.generate_content([prompt, image_parts[0]])
            
            # Extract JSON from response
            text = response.text
            # Remove markdown code blocks if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(text)
            return data
        except Exception as e:
            print(f"OCR Service Error: {e}")
            return None

# Singleton instance
ocr_service = OCRService()
