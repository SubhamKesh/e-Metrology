import cloudinary
import cloudinary.uploader
from app.config.settings import settings  # adjust import to match Deep's settings module

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
)

def upload_bytes(file_bytes: bytes, public_id: str, resource_type: str = "image") -> str:
    result = cloudinary.uploader.upload(
        file_bytes,
        public_id=public_id,
        resource_type=resource_type,   # "image" for QR/photos, "raw" for PDF
        overwrite=True,
    )
    return result["secure_url"]