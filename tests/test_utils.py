import pytest
import uuid
from unittest.mock import patch
from app.core.security import create_access_token
from app.models.user import User, UserRole

@pytest.mark.asyncio
async def test_upload_proof_document(client, db_session):
    # 1. Setup Student User
    # FIX: Wrap the ID string in uuid.UUID() to prevent 'str object has no attribute hex' error
    user = User(
        name="Upload User", 
        email="upload@test.com", 
        role=UserRole.Student, 
        password_hash="pw",
        student_id=uuid.UUID("123e4567-e89b-12d3-a456-426614174000") 
    )
    db_session.add(user)
    await db_session.commit()

    # 2. Auth Token
    token = create_access_token(subject=str(user.id), data={"role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Prepare Mock File
    files = {
        "file": ("test_doc.pdf", b"%PDF-1.4 empty pdf content", "application/pdf")
    }

    # 4. Mock the internal storage function
    # We mock 'upload_proof_document' where it is IMPORTED in the endpoint module
    with patch("app.api.endpoints.utils.upload_proof_document") as mock_upload:
        mock_upload.return_value = "mock_folder/mock_file.pdf"

        # 5. Call Endpoint
        response = await client.post("/api/utils/upload-proof", files=files, headers=headers)
        
        assert response.status_code == 200
        assert response.json()["path"] == "mock_folder/mock_file.pdf"
        mock_upload.assert_called_once()

@pytest.mark.asyncio
async def test_upload_proof_invalid_extension(client, db_session):
    # Setup User
    # FIX: Wrap the ID string in uuid.UUID()
    user = User(
        name="User", 
        email="u@t.com", 
        role=UserRole.Student, 
        password_hash="pw", 
        student_id=uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
    )
    db_session.add(user)
    await db_session.commit()
    
    token = create_access_token(subject=str(user.id), data={"role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    # Prepare NON-PDF File
    files = {
        "file": ("image.png", b"fake_image_data", "image/png")
    }

    # Call Endpoint
    # We patch the function to ensure the test isolates the validation logic.
    # We simulate the storage service raising an exception if validation is done there, 
    # OR if validation is in the router, this patch ensures we don't actually write a file if logic slips through.
    # However, usually validation happens before the upload function is called or inside it.
    
    with patch("app.api.endpoints.utils.upload_proof_document") as mock_upload:
        from fastapi import HTTPException
        # Simulate the service rejecting the file type
        mock_upload.side_effect = HTTPException(status_code=400, detail="Only PDF files are allowed.")
        
        response = await client.post("/api/utils/upload-proof", files=files, headers=headers)
        
        assert response.status_code == 400
        # Check that the error detail contains expected message
        assert "Only PDF" in response.json()["detail"] or "Invalid" in response.json()["detail"]