# app/services/turnstile.py
import httpx
from fastapi import HTTPException, Request
from app.core.config import settings

async def verify_turnstile(token: str, ip: str = None) -> bool:
    """
    Verifies the Turnstile token with Cloudflare's API.
    """
    # Skip verification in DEV mode if token is a dummy value (for development testing)
    if settings.DEBUG and token == "development-token-bypass":
        return True

    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    
    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
        "remoteip": ip
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, data=payload)
            response.raise_for_status()
            data = response.json()
            
            # success is True if validation passed
            if data.get("success"):
                return True
            
            # Log specific error codes for debugging if needed
            # error_codes = data.get("error-codes", [])
            # print(f"Turnstile Error: {error_codes}")
            
            return False
            
        except Exception as e:
            print(f"Turnstile Connection Error: {e}")
            return False