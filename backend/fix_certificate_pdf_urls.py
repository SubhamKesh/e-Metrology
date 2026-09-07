"""
One-off migration: fixes existing certificate documents whose pdf_url points
to a Cloudinary "raw" asset uploaded WITHOUT a .pdf extension in its
public_id. Those URLs serve real, valid PDF bytes, but with no file
extension for the browser/OS to recognize — so browsers fall back to
opening them as plain text (e.g. in Notepad) instead of downloading/viewing
them as a PDF.

What this script does, for every certificate whose pdf_url does NOT already
end in ".pdf":
  1. Downloads the existing PDF bytes from its current pdf_url.
  2. Re-uploads those same bytes to Cloudinary under a NEW public_id that
     ends in ".pdf" (resource_type="raw", same as cert_generator.py).
  3. Updates that certificate's pdf_url field in MongoDB to the new URL.

The old Cloudinary asset (extensionless) is left in place untouched — this
only adds a new asset and repoints the DB. Safe to re-run: certificates
whose pdf_url already ends in ".pdf" are skipped.

Run from the backend/ directory (same place you run uvicorn from), with
your venv active, so it picks up the same .env / MONGO_URI:

    python fix_certificate_pdf_urls.py

Add --dry-run to see what WOULD change without touching Cloudinary or the DB.
"""

import argparse
import sys

import requests

from app.config.db import certificates_col
from app.utils.upload_to_cloudinary import upload_bytes


def main(dry_run: bool) -> None:
    to_fix = list(certificates_col.find({"pdf_url": {"$not": {"$regex": r"\.pdf$"}}}))

    if not to_fix:
        print("Nothing to fix — every certificate's pdf_url already ends in .pdf.")
        return

    print(f"Found {len(to_fix)} certificate(s) with a non-.pdf pdf_url.")

    fixed = 0
    failed = 0

    for cert in to_fix:
        cert_id = cert["_id"]
        old_url = cert.get("pdf_url")

        if not old_url:
            print(f"  [{cert_id}] SKIP — no pdf_url on this document at all.")
            continue

        print(f"  [{cert_id}] old pdf_url: {old_url}")

        if dry_run:
            print(f"  [{cert_id}] DRY RUN — would download, re-upload as cert_{cert_id}.pdf, and update DB.")
            continue

        try:
            resp = requests.get(old_url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"  [{cert_id}] FAILED to download existing PDF: {exc}")
            failed += 1
            continue

        try:
            new_url = upload_bytes(resp.content, public_id=f"cert_{cert_id}.pdf", resource_type="raw")
        except Exception as exc:  # cloudinary.exceptions.Error, etc.
            print(f"  [{cert_id}] FAILED to re-upload to Cloudinary: {exc}")
            failed += 1
            continue

        certificates_col.update_one({"_id": cert_id}, {"$set": {"pdf_url": new_url}})
        print(f"  [{cert_id}] OK — new pdf_url: {new_url}")
        fixed += 1

    print()
    if dry_run:
        print(f"Dry run complete. {len(to_fix)} certificate(s) would be fixed.")
    else:
        print(f"Done. Fixed: {fixed}. Failed: {failed}.")
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without making any changes.")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
