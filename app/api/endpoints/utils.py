import redis.asyncio as redis
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request, status
from app.core.storage import upload_proof_document
from app.models.user import User, UserRole
from app.core.rbac import AllowRoles
from app.core.rate_limiter import limiter
from app.core.config import settings
from app.api.deps import get_current_user
from loguru import logger

router = APIRouter(prefix="/api/utils", tags=["Utilities"])

# ----------------------------------------------------------------
# 1. UPLOAD PROOF DOCUMENT
# ----------------------------------------------------------------
@router.post("/upload-proof")
async def upload_proof(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(AllowRoles(UserRole.Student))
):
    """
    Step 1 of Submission: Uploads the student's clearance PDF to private storage.
    Limited to 5 uploads per minute to prevent storage abuse.
    """
    if not current_user.student_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Student profile initialization required before uploading documents."
        )

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Only PDF documents are allowed."
        )

    try:
        file_path = await upload_proof_document(file, current_user.student_id)
        return {"path": file_path}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Critical Upload Failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to process file upload. Please try again later."
        )
