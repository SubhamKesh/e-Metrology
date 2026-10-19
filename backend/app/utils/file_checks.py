"""Checks for files people upload (profile pictures, supporting documents).

The browser-supplied filename and Content-Type are never trusted: the real type is read from the
first bytes of the file. Only the types below are accepted, and each has a size limit.
"""
from fastapi import HTTPException, UploadFile

MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024

IMAGE_KINDS = ("jpeg", "png", "webp")
DOCUMENT_KINDS = ("pdf", "jpeg", "png")
EXTENSION = {"pdf": "pdf", "jpeg": "jpg", "png": "png", "webp": "webp"}
MIME = {"pdf": "application/pdf", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def sniff(data: bytes) -> str | None:
    """pdf | jpeg | png | webp, from the file's own first bytes; None for anything else."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def read_checked(file: UploadFile, allowed: tuple[str, ...], max_bytes: int, what: str) -> tuple[bytes, str]:
    """Read an upload, refusing it if it is empty, too big or not one of the allowed types.
    Returns (bytes, kind). Reads at most max_bytes + 1 so a huge file is never pulled into memory."""
    data = await file.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail=f"The {what} file is empty.")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"The {what} must be {max_bytes // (1024 * 1024)} MB or smaller.")
    kind = sniff(data)
    if kind not in allowed:
        names = ", ".join({"jpeg": "JPG", "png": "PNG", "webp": "WebP", "pdf": "PDF"}[k] for k in allowed)
        raise HTTPException(status_code=415, detail=f"The {what} must be one of: {names}.")
    return data, kind
