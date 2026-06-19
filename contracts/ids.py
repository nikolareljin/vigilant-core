"""Dependency-free ULID generation for cross-node identifiers.

ULIDs are 26-character Crockford base32 strings whose leading 48 bits encode a
millisecond timestamp, so they sort lexicographically by creation time. That
time-ordering is what lets the store-and-forward queue and cross-node dedup
(``event_id``) work without a central clock or coordinator.
"""

from __future__ import annotations

import os
import time

# Crockford base32 alphabet (excludes I, L, O, U to avoid transcription errors).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_base32(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_CROCKFORD[rem])
    return "".join(reversed(chars))


def new_ulid(timestamp_ms: int | None = None) -> str:
    """Return a new 26-character ULID.

    ``timestamp_ms`` may be supplied for deterministic tests; otherwise the
    current wall-clock time is used. Randomness comes from ``os.urandom`` so the
    result is unguessable across nodes.
    """

    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    timestamp_ms &= (1 << 48) - 1
    randomness = int.from_bytes(os.urandom(10), "big")  # 80 bits
    return _encode_base32(timestamp_ms, 10) + _encode_base32(randomness, 16)
