from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

ALGO = "pbkdf2_sha256"


def hash_password(password: str, *, iterations: int = 260_000, salt: Optional[bytes] = None) -> str:
    """Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>"""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = encoded.split("$", 3)
        if algo != ALGO:
            return False
        iterations = int(iters)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False
