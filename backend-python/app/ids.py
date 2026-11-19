"""Prefixed, time-sortable identifiers (ULID layout: 48-bit ms time + 80 random bits)."""
from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32


def _b32(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        out.append(_ALPHABET[rem])
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    stamp = int(time.time() * 1000) & ((1 << 48) - 1)
    return f"{prefix}_{_b32(stamp, 10)}{_b32(secrets.randbits(80), 16)}"
