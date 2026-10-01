"""A secret at rest, sealed with a password: PBKDF2-HMAC-SHA256 (250,000 rounds) -> AES-256-GCM.

The blob ``{"v": 1, "salt", "iv", "ct"}`` (base64 fields; ``ct`` = ciphertext || 16-byte tag) is byte-compatible with
the TypeScript, Dart and Kotlin SDK vaults (conformance fixture ``vault-fixture.json``).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Mapping
from typing import Any

from Crypto.Cipher import AES

VAULT_VERSION = 1
VAULT_ITERATIONS = 250_000


class VaultError(Exception):
    """Wrong password, a tampered blob, or an unsupported vault version."""


def _key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, VAULT_ITERATIONS, 32)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def encrypt_vault(secret: str, password: str) -> dict[str, Any]:
    """Seal ``secret`` under ``password``. Randomized: a fresh salt and IV on every call."""
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    ct, tag = AES.new(_key(password, salt), AES.MODE_GCM, nonce=iv).encrypt_and_digest(secret.encode("utf-8"))
    return {"v": VAULT_VERSION, "salt": _b64(salt), "iv": _b64(iv), "ct": _b64(ct + tag)}


def decrypt_vault(blob: Mapping[str, Any], password: str) -> str:
    """Open a blob. Raises :class:`VaultError` on a wrong password or a tampered blob (GCM tag mismatch)."""
    if not isinstance(blob, Mapping) or blob.get("v") != VAULT_VERSION:
        raise VaultError(f"unsupported vault version {blob.get('v') if isinstance(blob, Mapping) else None!r}")
    try:
        salt, iv, data = (base64.b64decode(blob[k], validate=True) for k in ("salt", "iv", "ct"))
        if len(data) < 16:
            raise ValueError("ciphertext too short")
        return AES.new(_key(password, salt), AES.MODE_GCM, nonce=iv).decrypt_and_verify(data[:-16], data[-16:]).decode("utf-8")
    except (KeyError, ValueError, TypeError) as e:
        raise VaultError("wrong password or corrupted vault") from e
