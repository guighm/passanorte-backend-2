"""Shared field-crypto primitives (RNF08; research R1).

- ``encrypt_value``/``decrypt_value``: Fernet (AES-128-CBC + HMAC, random
  IV) for sensitive values at rest — confidentiality only.
- ``lookup_hash``: HMAC-SHA256 keyed lookup for equality search/uniqueness
  (email, cpf, passport) — deterministic, context-separated.

The lookup key is derived from the Fernet key via HKDF (fixed salt, distinct
``info`` per context) — a second secret in env is never needed (research R2).
Repositories never persist plaintext; decryption happens only in services
(controlled decryption — SC-005).
"""

import hashlib
import hmac as stdlib_hmac
from typing import Final

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

LOOKUP_HASH_LENGTH: Final[int] = 64
_HKDF_SALT: Final[bytes] = b"passanorte-lookup-hash-v1"
_FERNET_KEY_LENGTH: Final[int] = 32


class CryptoKeyMissingError(RuntimeError):
    """Sensitive-data key absent/empty (RNF08 — secrets in env, never code)."""


class DecryptionError(RuntimeError):
    """Ciphertext cannot be decrypted with the configured key."""


def _fernet(key: bytes) -> Fernet:
    if not key or not key.strip():
        raise CryptoKeyMissingError("sensitive data key is empty — set SENSITIVE_DATA_KEY")
    return Fernet(key)


def encrypt_value(value: str, key: bytes) -> str:
    """Encrypt a sensitive value with Fernet (token string, random IV)."""
    return _fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_value(ciphertext: str, key: bytes) -> str:
    """Decrypt a stored Fernet token (controlled-decryption flows only)."""
    fernet = _fernet(key)
    try:
        return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as error:
        raise DecryptionError("cannot decrypt value with the configured key") from error


def _lookup_signing_key(key: bytes, *, context: str) -> bytes:
    """HKDF-derived subkey: one key in env, one subkey per lookup context."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_FERNET_KEY_LENGTH,
        salt=_HKDF_SALT,
        info=f"lookup:{context}".encode(),
    )
    return hkdf.derive(key)


def lookup_hash(value: str, *, context: str, key: bytes) -> str:
    """Keyed HMAC-SHA256 of ``value`` in the given context (64 hex chars).

    Deterministic by design (equality/indexing/uniqueness); the context is
    domain-separated via HKDF ``info`` — equal values in different contexts
    never collide. Callers normalize (trim/casefold) before hashing.
    """
    if not key or not key.strip():
        raise CryptoKeyMissingError("sensitive data key is empty — set SENSITIVE_DATA_KEY")
    signing_key = _lookup_signing_key(key, context=context)
    digest = stdlib_hmac.new(signing_key, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:LOOKUP_HASH_LENGTH]
