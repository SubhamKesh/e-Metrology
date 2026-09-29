"""
Generates the government-style unique instrument ID (UIID) referenced in
the anti-substitution design: every registered instrument gets one fixed
identity string that never changes, independent of its serial number.

Format: LM-<2-digit year>-<7-char base36 code><1 check char>
  e.g. LM-26-3K9QXWP7  (exact digits vary per instrument)

Why not a bare sequential "LM-000008":
  - uiid is looked up publicly (see routers/instruments.py:
    get_instrument_by_uiid — what a QR scan resolves to during field
    verification). A raw auto-increment number lets anyone enumerate
    every other registered instrument just by walking the integer
    sequence, and it leaks the total registration count to anyone who
    notices the pattern.
  - Real government-issued IDs (PAN, vehicle registration, GSTIN, etc.)
    read as a structured-but-opaque code with a trailing check
    character, not a bare incrementing number — this mimics that shape.

Still backed by the exact same atomic MongoDB counter as before — only
the *presentation* of the sequence number changed, not how uniqueness is
guaranteed. The scrambling step (multiplicative hashing mod 2**32) is a
bijection: multiplying by an odd constant modulo a power of two maps
every distinct sequence number to exactly one distinct scrambled value,
so uniqueness is inherited directly from the counter, not re-derived.
This is obfuscation for anyone glancing at the ID, not a cryptographic
secret — the multiplier below is a public, well-known constant (Knuth's
multiplicative hash constant), not something meant to resist a
determined attacker trying to reverse it. Given that, the trailing
check character is a plain positional checksum (catches an accidentally
mistyped/transposed character, the way a real ID's check digit would),
not a security control either.

Deliberately still NOT encoding state/district in the format — unlike
when this was originally written, Instrument.location is no longer
free text (see app/models/geo.py: LocationIn), it's now a structured
state_code/district_code pair, so that's no longer a blocker. Left out
here anyway to avoid changing generate_uiid()'s signature/call site as
part of an "obscure the ID" change; folding location.state_code into
the format is a reasonable follow-up if you want it, just a separate
change.

2**32 is used as the modulus purely for headroom (billions of possible
instruments) — collisions are only theoretically possible if the
counter itself ever reached that many registrations, at which point the
counter's own atomicity is what's actually being relied on, same as
before this change.
"""

from datetime import datetime, timezone

from pymongo import ReturnDocument

from app.config.db import counters_col

COUNTER_NAME = "instrument_uiid"

_BASE36_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_MODULUS = 2**32  # headroom far beyond any realistic instrument count
_MULTIPLIER = 2654435761  # Knuth's multiplicative hash constant — odd, so
# coprime to 2**32, which is exactly what makes the mapping below a
# bijection over the modulus (distinct seq -> distinct scrambled value)
_CODE_LENGTH = 7  # 36**7 ≈ 78 trillion codes; enough to represent every
# value up to 2**32-1 (36**6 ≈ 2.18 billion would NOT be enough)


def _base36(n: int, width: int) -> str:
    if n == 0:
        digits = "0"
    else:
        digits = ""
        while n:
            n, rem = divmod(n, 36)
            digits = _BASE36_ALPHABET[rem] + digits
    return digits.rjust(width, "0")


def _check_char(code: str) -> str:
    """Simple positional-weighted checksum over the code. Catches a
    single mistyped or transposed character the way a real ID's trailing
    check digit would — not meant as a security control."""
    total = sum((i + 1) * _BASE36_ALPHABET.index(ch) for i, ch in enumerate(code))
    return _BASE36_ALPHABET[total % 36]


def generate_uiid() -> str:
    result = counters_col.find_one_and_update(
        {"_id": COUNTER_NAME},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = result["seq"]

    scrambled = (seq * _MULTIPLIER) % _MODULUS
    code = _base36(scrambled, _CODE_LENGTH)
    check = _check_char(code)

    year = datetime.now(timezone.utc).strftime("%y")
    return f"LM-{year}-{code}{check}"