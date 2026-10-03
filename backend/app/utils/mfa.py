"""Helpers for two-step verification secrets and recovery codes.

- TOTP secrets are encrypted at rest (Fernet: AES-128-CBC + HMAC), so a
  database leak or backup does not hand out working second factors.
- Recovery codes are shown to the user once and stored only as keyed hashes.
"""
import base64
import hashlib
import hmac
import io
import secrets

import qrcode
from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import JWT_SECRET, MFA_ENCRYPTION_KEY, MFA_RECOVERY_CODE_COUNT

# No 0/o/1/l/i — easy to misread when copied from paper.
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def _key_material(purpose: bytes) -> bytes:
    base = (MFA_ENCRYPTION_KEY or JWT_SECRET).encode("utf-8")
    return hashlib.sha256(purpose + b"\x00" + base).digest()


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_key_material(b"maapsetu-mfa-secret-v1")))


def encrypt_secret(secret_b32: str) -> str:
    return _fernet().encrypt(secret_b32.encode("ascii")).decode("ascii")


def decrypt_secret(token: str) -> str | None:
    """None if the value can't be decrypted (wrong key / corrupted)."""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError):
        return None


def generate_recovery_codes(count: int = MFA_RECOVERY_CODE_COUNT) -> list[str]:
    """e.g. 'k7m2x-q9d4p' — 10 random characters (~49 bits) each."""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum())


def hash_recovery_code(code: str) -> str:
    key = _key_material(b"maapsetu-mfa-recovery-v1")
    return hmac.new(key, normalize_recovery_code(code).encode("utf-8"), hashlib.sha256).hexdigest()


def qr_data_uri(text: str) -> str:
    """PNG QR code as a data: URI, so the frontend needs no QR library."""
    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
