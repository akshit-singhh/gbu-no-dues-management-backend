# app/core/security.py
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from typing import Optional
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
MAX_BCRYPT_BYTES = 72  # bcrypt max bytes

def _truncate_password(password: str) -> str:
    """
    Truncate password to 72 bytes safely for bcrypt.
    Returns a UTF-8 string that is safe for hashing.
    """
    encoded = password.encode("utf-8")[:MAX_BCRYPT_BYTES]
    return encoded.decode("utf-8", "ignore")

def hash_password(password: str) -> str:
    """
    Hash password using bcrypt, safely truncated.
    """
    safe_password = _truncate_password(password)
    return pwd_context.hash(safe_password)

def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify password using bcrypt, safely truncated.
    """
    safe_plain = _truncate_password(plain)
    return pwd_context.verify(safe_plain, hashed)

def create_access_token(
    subject: str,
    data: Optional[dict] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.
    """
    to_encode = {"sub": subject}
    if data:
        to_encode.update(data)
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token

def decode_token(token: str) -> dict:
    """
    Decode a JWT token.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise e
