"""Commitments and hash chain of the event log (SPEC section 7). SHA-256, `||` = concatenation.

    c_i = H(s_i || enc(r_i))          s_i: 32 fresh random bytes per record
    h_i = H(h_{i-1} || c_i || i)      i: position in the chain, 8 bytes big-endian
    h_0 = H(session)                  session id, UTF-8

`enc` = canonical JSON: sorted keys, no whitespace, UTF-8 (non-ASCII kept as is). Hashes
are combined as raw bytes and stored as lowercase hex.
"""

import hashlib
import json
import secrets
from typing import Any


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def new_salt() -> str:
    return secrets.token_hex(32)


def commitment(salt: str, record: dict[str, Any]) -> str:
    return hashlib.sha256(bytes.fromhex(salt) + canonical(record)).hexdigest()


def genesis(session: str) -> str:
    return hashlib.sha256(session.encode()).hexdigest()


def link(previous: str, commitment_hex: str, position: int) -> str:
    data = bytes.fromhex(previous) + bytes.fromhex(commitment_hex) + position.to_bytes(8, "big")
    return hashlib.sha256(data).hexdigest()
