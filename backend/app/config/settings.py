import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "maapsetu")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "10080"))  # 7 days

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

# Public URL of the verify-page app (Aritra + Anushka). The QR code on every
# certificate points here + "/{cert_id}". Set this in .env once verify-page
# is deployed — falls back to localhost for local dev against `next dev`.
FRONTEND_VERIFY_URL = os.getenv("FRONTEND_VERIFY_URL", "http://localhost:3001/verify")


class _Settings:
    """
    Object-style access to the same values above, e.g. settings.CLOUDINARY_API_KEY.
    Exists because qr_generator.py and upload_to_cloudinary.py (Kiran) import
    `settings` as an object rather than the flat module-level names — both
    styles now work, so nobody has to change their existing import.
    """
    MONGO_URI = MONGO_URI
    DB_NAME = DB_NAME
    JWT_SECRET = JWT_SECRET
    JWT_ALGORITHM = JWT_ALGORITHM
    JWT_EXPIRES_MINUTES = JWT_EXPIRES_MINUTES
    CLOUDINARY_CLOUD_NAME = CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY = CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET = CLOUDINARY_API_SECRET
    FRONTEND_VERIFY_URL = FRONTEND_VERIFY_URL


settings = _Settings()
