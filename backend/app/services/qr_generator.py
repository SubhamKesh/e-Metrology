import qrcode
from io import BytesIO
from app.config.settings import settings
from app.utils.upload_to_cloudinary import upload_bytes

def generate_qr(cert_id: str) -> str:
    url = f"{settings.FRONTEND_VERIFY_URL}/{cert_id}"  # points to verify-page/, not the API
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return upload_bytes(buf.getvalue(), public_id=f"qr_{cert_id}", resource_type="image")