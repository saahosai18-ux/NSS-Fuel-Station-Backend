import os
import json
import base64
import httpx
import google.generativeai as genai
from typing import Optional, Dict, Any

class OCRService:
    def __init__(self):
        # Configure Gemini
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Keys for fallbacks
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY")

    async def extract_receipt_data(self, image_bytes: bytes, receipt_type: str = "opening") -> Optional[Dict[str, Any]]:
        """
        Extracts Vtot readings and timestamp from a receipt image.
        Tries Gemini -> OpenRouter -> Groq.
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

        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{base64_image}"
        
        errors = []
        extracted_data = None
        used_provider = None

        # --- Provider 1: Gemini ---
        if self.gemini_api_key:
            gemini_models = ['gemini-2.0-flash', 'gemini-2.5-flash', 'gemini-flash-latest', 'gemini-pro-latest']
            
            for model_name in gemini_models:
                try:
                    print(f"OCR: Attempting Gemini model {model_name}...")
                    model = genai.GenerativeModel(model_name)
                    image_parts = [{"mime_type": "image/jpeg", "data": image_bytes}]
                    response = model.generate_content([prompt, image_parts[0]])
                    
                    text = response.text
                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0].strip()
                    elif "```" in text:
                        text = text.split("```")[1].split("```")[0].strip()
                    
                    extracted_data = json.loads(text)
                    used_provider = f"Gemini ({model_name})"
                    break  # Success! Stop trying other models
                except Exception as e:
                    print(f"Gemini {model_name} Error: {e}")
                    errors.append(f"Gemini {model_name}: {str(e)}")
                    continue # Try the next model

        # --- Provider 2: OpenRouter (Fallback) ---
        if not extracted_data and self.openrouter_api_key:
            try:
                print("OCR: Gemini failed, attempting OpenRouter...")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.openrouter_api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "meta-llama/llama-3.2-11b-vision-instruct:free",
                            "messages": [{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": data_uri}}
                                ]
                            }]
                        },
                        timeout=30.0
                    )
                    response.raise_for_status()
                    result = response.json()
                    text = result["choices"][0]["message"]["content"]
                    
                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0].strip()
                    elif "```" in text:
                        text = text.split("```")[1].split("```")[0].strip()
                        
                    extracted_data = json.loads(text)
                    used_provider = "OpenRouter (Llama 3.2 Vision)"
            except Exception as e:
                print(f"OpenRouter Error: {e}")
                errors.append(f"OpenRouter: {str(e)}")

        # --- Provider 3: Groq (Fallback) ---
        if not extracted_data and self.groq_api_key:
            try:
                print("OCR: OpenRouter failed, attempting Groq...")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.groq_api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "llama-3.2-11b-vision-preview",
                            "messages": [{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": data_uri}}
                                ]
                            }]
                        },
                        timeout=30.0
                    )
                    response.raise_for_status()
                    result = response.json()
                    text = result["choices"][0]["message"]["content"]
                    
                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0].strip()
                    elif "```" in text:
                        text = text.split("```")[1].split("```")[0].strip()
                        
                    extracted_data = json.loads(text)
                    used_provider = "Groq (Llama 3.2 Vision Preview)"
            except Exception as e:
                print(f"Groq Error: {e}")
                errors.append(f"Groq: {str(e)}")

        # --- Final Verification ---
        if extracted_data:
            extracted_data["provider"] = used_provider
            print(f"OCR Success using {used_provider}")
            return extracted_data
        else:
            print(f"All OCR providers failed. Errors: {errors}")
            return None

# Singleton instance
ocr_service = OCRService()
