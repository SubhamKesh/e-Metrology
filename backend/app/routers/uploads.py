from fastapi import APIRouter, UploadFile, File, Depends
from app.utils.upload_to_cloudinary import upload_bytes
from app.middleware.auth import get_current_user
import uuid

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])


@router.post("/photo")
async def upload_photo(file: UploadFile = File(...), user=Depends(get_current_user)):
    contents = await file.read()
    url = upload_bytes(contents, public_id=f"photo_{uuid.uuid4()}", resource_type="image")
    return {"url": url}