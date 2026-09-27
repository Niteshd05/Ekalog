"""Ed25519 signing for parser artifacts, packs and ledger checkpoints (local key, never leaves the box)."""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..config import settings


@lru_cache(maxsize=1)
def _key() -> Ed25519PrivateKey:
    path = settings.state_dir / "ed25519.key"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    k = Ed25519PrivateKey.generate()
    path.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    return k


def public_key_b64() -> str:
    raw = _key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def fingerprint(pub_b64: str | None = None) -> str:
    pub = base64.b64decode(pub_b64 or public_key_b64())
    return hashlib.sha256(pub).hexdigest()[:16]


def sign(data: bytes) -> str:
    return base64.b64encode(_key().sign(data)).decode()


def verify(data: bytes, sig_b64: str, pub_b64: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(base64.b64decode(sig_b64), data)
        return True
    except (InvalidSignature, ValueError):
        return False
