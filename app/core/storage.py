#app/core/storage.py

import os
import io
import uuid
import ssl
from typing import Any
from fastapi import UploadFile, HTTPException
from ftplib import FTP, FTP_TLS, error_perm

# =====================================================================
# CUSTOM FTP_TLS CLASS (Fixes the 425 TLS Session Resumption Error)
# =====================================================================
class ResumedFTP_TLS(FTP_TLS):
    """Extension of FTP_TLS to support TLS session resumption on the data channel."""
    def ntransfercmd(self, cmd, rest=None):
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session 
            )
        return conn, size
# =====================================================================

# Optional Supabase imports
try:
    from supabase import create_client, Client
    SupabaseClientType = Client
except ImportError:
    create_client = None
    SupabaseClientType = Any

# ------------------------
# 1. Load Config (The Master Toggle)
# ------------------------
# Looks for "STORAGE" first, falls back to "STORAGE_BACKEND", defaults to "FTP"
STORAGE_BACKEND = os.environ.get("STORAGE", os.environ.get("STORAGE_BACKEND", "FTP")).upper()

# Supabase Config
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
BUCKET_NAME = "application-docs"

# FTP Config
FTP_HOST = os.environ.get("FTP_HOST")
FTP_PORT = int(os.environ.get("FTP_PORT", 21))
FTP_USER = os.environ.get("FTP_USER")
FTP_PASSWORD = os.environ.get("FTP_PASSWORD")
FTP_PASSIVE_MODE = os.environ.get("FTP_PASSIVE_MODE", "True").lower() in ("true", "1", "yes")
FTP_UPLOAD_DIR = os.environ.get("FTP_UPLOAD_DIR", "/uploads") 
FTP_USE_TLS = os.environ.get("FTP_USE_TLS", "True").lower() in ("true", "1", "yes")

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# ------------------------
# 2. Initialize Supabase (If Selected)
# ------------------------
supabase: SupabaseClientType | None = None # type: ignore

if STORAGE_BACKEND == "SUPABASE":
    if SUPABASE_URL and SUPABASE_KEY and create_client:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Supabase Storage Initialized")
        except Exception as e:
            print(f"⚠️ Supabase Init Failed: {e}. Falling back to FTP.")
            supabase = None
            STORAGE_BACKEND = "FTP"
    else:
        print("⚠️ Supabase credentials missing in .env. Falling back to FTP.")
        STORAGE_BACKEND = "FTP"

# ------------------------
# 3. Upload function
# ------------------------
async def upload_proof_document(file: UploadFile, student_id: uuid.UUID) -> str:
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF files are allowed.")

    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large. Max size is {MAX_FILE_SIZE // (1024*1024)}MB.")
    await file.seek(0)

    safe_filename = f"{uuid.uuid4()}.pdf"
    file_path = f"{student_id}/{safe_filename}"

    # --- SUPABASE UPLOAD ---
    if STORAGE_BACKEND == "SUPABASE" and supabase:
        try:
            supabase.storage.from_(BUCKET_NAME).upload(
                path=file_path,
                file=file_content,
                file_options={"content-type": "application/pdf", "upsert": "true"}
            )
            return file_path
        except Exception as e:
            print(f"❌ Supabase Upload Error: {e}")
            raise HTTPException(500, "Failed to upload document to cloud storage.")

    # --- FTP UPLOAD ---
    elif STORAGE_BACKEND == "FTP":
        if not all([FTP_HOST, FTP_USER, FTP_PASSWORD]):
            raise HTTPException(500, "FTP credentials missing.")

        try:
            if FTP_USE_TLS:
                ftps = ResumedFTP_TLS()
                ftps.connect(host=FTP_HOST, port=FTP_PORT, timeout=30)
                ftps.auth()            
                ftps.login(user=FTP_USER, passwd=FTP_PASSWORD)
                ftps.prot_p()          
            else:
                ftps = FTP()
                ftps.connect(host=FTP_HOST, port=FTP_PORT, timeout=30)
                ftps.login(user=FTP_USER, passwd=FTP_PASSWORD)

            ftps.set_pasv(FTP_PASSIVE_MODE)

            student_dir = f"{FTP_UPLOAD_DIR}/{student_id}"
            try:
                ftps.cwd(student_dir)
            except error_perm:
                parts = student_dir.strip("/").split("/")
                path_accum = ""
                for part in parts:
                    if not part: continue
                    path_accum += f"/{part}"
                    try:
                        ftps.mkd(path_accum)
                    except error_perm:
                        pass
                ftps.cwd(student_dir)

            try:
                ftps.storbinary(f"STOR {safe_filename}", file.file)
            except ssl.SSLEOFError:
                pass
            
            ftps.quit()
            return f"{student_dir}/{safe_filename}"

        except Exception as e:
            print(f"❌ FTP Upload Error: {e}")
            raise HTTPException(500, "Failed to upload document to FTP server.")

    else:
        raise HTTPException(500, "Invalid storage backend.")

# ------------------------
# 5. Signed URL
# ------------------------
def get_signed_url(file_path: str, expiration=3600) -> str:
    if STORAGE_BACKEND == "SUPABASE" and supabase:
        try:
            response = supabase.storage.from_(BUCKET_NAME).create_signed_url(file_path, expiration)
            return response.get("signedURL") if isinstance(response, dict) else getattr(response, "signedURL", str(response))
        except Exception:
            return None
    elif STORAGE_BACKEND == "FTP":
        return file_path
    return None

# ------------------------
# 6. FTP Connection Check
# ------------------------
def check_ftp_connection() -> bool:
    if STORAGE_BACKEND != "FTP":
        return True # Skip FTP check if using Supabase

    if not all([FTP_HOST, FTP_USER, FTP_PASSWORD]):
        return False
    try:
        if FTP_USE_TLS:
            ftps = ResumedFTP_TLS()
            ftps.connect(host=FTP_HOST, port=FTP_PORT, timeout=10)
            ftps.auth()      
            ftps.login(user=FTP_USER, passwd=FTP_PASSWORD)
            ftps.prot_p()    
        else:
            ftps = FTP()
            ftps.connect(host=FTP_HOST, port=FTP_PORT, timeout=10)
            ftps.login(user=FTP_USER, passwd=FTP_PASSWORD)
            
        ftps.cwd("/")     
        ftps.quit()
        return True
    except Exception as e:
        print(f"❌ FTP connection failed: {e}")
        return False

# ------------------------
# 7. Download from FTP (NEW)
# ------------------------
def download_from_ftp(file_path: str) -> bytes | None:
    """Downloads a file from the FTP server and returns its bytes."""
    if not all([FTP_HOST, FTP_USER, FTP_PASSWORD]):
        print("❌ FTP credentials missing for download.")
        return None
        
    try:
        pdf_buffer = io.BytesIO()
        if FTP_USE_TLS:
            ftp = ResumedFTP_TLS()
            ftp.connect(host=FTP_HOST, port=FTP_PORT, timeout=10)
            ftp.auth()
            ftp.login(user=FTP_USER, passwd=FTP_PASSWORD)
            ftp.prot_p()
        else:
            ftp = FTP()
            ftp.connect(host=FTP_HOST, port=FTP_PORT, timeout=10)
            ftp.login(user=FTP_USER, passwd=FTP_PASSWORD)

        ftp.set_pasv(FTP_PASSIVE_MODE)
        
        # Download the file directly into memory
        ftp.retrbinary(f"RETR {file_path}", pdf_buffer.write)
        ftp.quit()
        
        return pdf_buffer.getvalue()
    except Exception as e:
        print(f"❌ FTP Download Error: {e}")
        return None