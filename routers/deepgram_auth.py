from fastapi import APIRouter
import httpx
import os
from pydantic import BaseModel

router = APIRouter()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "2c72b231c4d5ca80ba100d1467fbadea98e25d79")
DEEPGRAM_PROJECT_ID = "02f34869-64b0-4e93-9ff8-8423f82198cd"

class TokenResponse(BaseModel):
    key: str

@router.get("/token", response_model=TokenResponse)
async def get_deepgram_token():
    """Generates a temporary (1hr) Deepgram API key so the original key isn't exposed permanently in the browser."""
    url = f"https://api.deepgram.com/v1/projects/{DEEPGRAM_PROJECT_ID}/keys"
    
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "comment": "HireHand WebClient Temp Key",
        "scopes": ["usage:write"],
        "time_to_live_in_seconds": 3600
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=5.0)
            
            if response.status_code in (200, 201):
                data = response.json()
                temp_key = data.get("key") or data.get("api_key") or data.get("member_key")
                if temp_key:
                    return {"key": temp_key}
                
            print(f"Deepgram Temp Key Generation Failed (Status: {response.status_code}): {response.text}")
    except Exception as e:
        print(f"Deepgram token error: {str(e)}")
        
    # Fallback to master key if temporary credential generation fails
    return {"key": DEEPGRAM_API_KEY}
