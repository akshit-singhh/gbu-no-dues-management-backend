#app/core/rate_limiter.py

import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings
from loguru import logger
import redis.asyncio as redis

# ----------------------------------------------------------------
# 1. ADVANCED IP IDENTIFICATION
# ----------------------------------------------------------------
def get_real_ip(request):
    """
    Standard industry practice for identifying client IP behind proxies.
    Checks X-Forwarded-For (Vercel/Nginx) and X-Real-IP (Cloudflare).
    """
    # Try X-Forwarded-For first (most common for Vercel/Load Balancers)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Get the leftmost IP (the actual client)
        return forwarded.split(",")[0].strip()
    
    # Fallback to X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
        
    return get_remote_address(request)

# ----------------------------------------------------------------
# 2. REDIS CONNECTION STRING HANDLING (SSL/TLS Support)
# ----------------------------------------------------------------
# Industry standard: Managed Redis (Upstash, DigitalOcean, AWS) 
# usually requires 'rediss://' (with two 's') for SSL.
storage_uri = settings.REDIS_URL

if storage_uri and storage_uri.startswith("redis://") and not os.environ.get("DEV_MODE"):
    # Force SSL for production environments if not already set
    storage_uri = storage_uri.replace("redis://", "rediss://", 1)

# ----------------------------------------------------------------
# 3. INITIALIZE LIMITER WITH FAIL-OVER LOGIC
# ----------------------------------------------------------------
try:
    if storage_uri:
        logger.info("⚡ Initializing Rate Limiter with Redis Storage")
        limiter = Limiter(
            key_func=get_real_ip,
            storage_uri=storage_uri,
            # Production tuning:
            strategy="fixed-window", # or "moving-window" for more precision
            storage_options={"socket_connect_timeout": 5, "retry_on_timeout": True}
        )
    else:
        logger.warning("⚠️ REDIS_URL not found. Falling back to In-Memory rate limiting.")
        limiter = Limiter(key_func=get_real_ip)

except Exception as e:
    logger.error(f"❌ Failed to connect to Redis for Rate Limiting: {e}")
    # CRITICAL: Always fallback to memory so the API stays alive
    limiter = Limiter(key_func=get_real_ip)
