"""RFC 6238 time-based one-time passwords (what Google Authenticator,
Microsoft Authenticator, Authy, etc. generate), implemented with the standard
library only — SHA-1, 6 digits, 30-second steps, the combination every
authenticator app supports. Checked against the RFC's published test vectors
in tests/test_mfa.py.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

TOTP_DIGITS = 6
TOTP_PERIOD = 30


def generate_secret() -> str:
    """160 random bits as unpadded base32 (20 bytes -> 32 chars, no padding needed)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def current_step(for_time: float | None = None) -> int:
    return int((time.time() if for_time is None else for_time) // TOTP_PERIOD)


def _code_for_step(secret_b32: str, step: int) -> str:
    key = base64.b32decode(secret_b32, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def totp_at(secret_b32: str, for_time: float | None = None) -> str:
    """The code an authenticator app would show right now (used by tests)."""
    return _code_for_step(secret_b32, current_step(for_time))


def verify_totp(
    secret_b32: str,
    code: str,
    *,
    last_step: int | None = None,
    window: int = 1,
    for_time: float | None = None,
) -> int | None:
    """Returns the matched time-step, or None.

    Accepts the current step and `window` steps either side (clock drift).
    Steps <= `last_step` are never accepted: a code that was already used
    can't be used again inside its validity window. Every candidate is
    compared in constant time.
    """
    if not (code.isascii() and code.isdigit() and len(code) == TOTP_DIGITS):
        return None
    now = current_step(for_time)
    matched: int | None = None
    for step in range(now - window, now + window + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(_code_for_step(secret_b32, step), code):
            matched = step
    return matched


def provisioning_uri(secret_b32: str, account: str, issuer: str) -> str:
    """otpauth:// URI that authenticator apps read from the QR code."""
    label = quote(f"{issuer}:{account}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"
    )
