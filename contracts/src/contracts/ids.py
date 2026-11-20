"""Prefixed ULID ids, timestamps and canonical JSON hashing.

A ULID is 48 bits of millisecond time plus 80 random bits, written as
26 Crockford base32 characters. Ids sort by creation time.
"""

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

ID_PREFIXES = ("ses", "ins", "tp", "tc", "code", "run", "rep", "call", "resp", "clr")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid(timestamp_ms: int | None = None) -> str:
    """Return a new 26-character ULID string."""
    if timestamp_ms is None:
        timestamp_ms = time.time_ns() // 1_000_000
    value = (timestamp_ms << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    """Return a prefixed id such as `ses_01JD...`."""
    if prefix not in ID_PREFIXES:
        raise ValueError(f"unknown id prefix: {prefix!r}")
    return f"{prefix}_{ulid()}"


def is_id(value: str, prefix: str) -> bool:
    head, sep, tail = value.partition("_")
    return head == prefix and sep == "_" and len(tail) == 26 and all(c in _CROCKFORD for c in tail)


def utc_now() -> datetime:
    """Current time in UTC, truncated to milliseconds."""
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def canonical_json(value: Any) -> bytes:
    """Canonical JSON bytes used for hashing and diffs (AD-5)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_sha256(content: Any) -> str:
    """SHA-256 hex digest of the canonical JSON of `content` only (AD-5)."""
    return hashlib.sha256(canonical_json(content)).hexdigest()
