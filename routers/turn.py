"""
TURN Server Credentials Endpoint
Fetches temporary ICE/TURN credentials from Metered.ca REST API.
Frontend calls this endpoint to get TURN servers for WebRTC NAT traversal.
All API keys stay securely on the backend.
"""
from fastapi import APIRouter, HTTPException
import httpx
import os

router = APIRouter()

METERED_API_KEY = os.getenv("METERED_API_KEY")
METERED_APP_NAME = os.getenv("METERED_APP_NAME", "hirehand")


@router.get("/turn-credentials")
async def get_turn_credentials():
    """
    Fetches temporary TURN server credentials from the Metered.ca API.
    Returns an array of iceServers that the frontend can directly use
    in RTCPeerConnection config.
    """
    if not METERED_API_KEY:
        raise HTTPException(status_code=500, detail="TURN server not configured")

    url = f"https://{METERED_APP_NAME}.metered.live/api/v1/turn/credentials?apiKey={METERED_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            ice_servers = response.json()
            print(f"✅ Fetched {len(ice_servers)} ICE/TURN servers from Metered")
            return ice_servers
    except Exception as e:
        print(f"❌ Failed to fetch TURN credentials: {e}")
        # Fallback to STUN-only if TURN API fails
        return [
            {"urls": "stun:stun.l.google.com:19302"},
            {"urls": "stun:stun1.l.google.com:19302"},
            {"urls": "stun:stun2.l.google.com:19302"},
        ]
