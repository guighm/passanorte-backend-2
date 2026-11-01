"""Unit: shared crypto primitives in ``core.crypto`` (research R1; T003).

Roundtrip via Fernet, deterministic lookup hashes, context separation and
the explicit error for a missing key (RNF08).

The test key is synthetic — generated at fixture time, never a real secret
(quality gate: no sensitive data in tests).
"""

import pytest
from cryptography.fernet import Fernet

from passanorte_back.core.crypto import (
    CryptoKeyMissingError,
    decrypt_value,
    encrypt_value,
    lookup_hash,
)


@pytest.fixture
def key() -> bytes:
    """Fresh Fernet key per test (ephemeral — FR-011)."""
    return Fernet.generate_key()


def test_roundtrip_encrypt_decrypt(key: bytes) -> None:
    ciphertext = encrypt_value("ana@example.com", key)
    assert ciphertext != "ana@example.com"
    assert decrypt_value(ciphertext, key) == "ana@example.com"


def test_ciphertext_is_not_plaintext_and_differs_per_call(key: bytes) -> None:
    first = encrypt_value("secret value", key)
    second = encrypt_value("secret value", key)
    assert first != second  # random IV — never a deterministic ciphertext
    assert "secret" not in first


def test_lookup_hash_is_deterministic_and_64_hex(key: bytes) -> None:
    first = lookup_hash("ana@example.com", context="email", key=key)
    second = lookup_hash(" ana@example.com ".strip().casefold(), context="email", key=key)
    assert first == second
    assert len(first) == 64
    assert int(first, 16) >= 0  # lowercase hex


def test_lookup_hash_differs_for_distinct_values(key: bytes) -> None:
    assert lookup_hash("a@example.com", context="email", key=key) != lookup_hash(
        "b@example.com", context="email", key=key
    )


def test_lookup_hash_separates_contexts(key: bytes) -> None:
    """Same value in different contexts (cpf vs email) → different lookups."""
    same = "11223344556"
    assert lookup_hash(same, context="cpf", key=key) != lookup_hash(same, context="email", key=key)
    assert lookup_hash(same, context="cpf", key=key) != lookup_hash(
        same, context="passport", key=key
    )


def test_lookup_hash_differs_for_other_users(key: bytes) -> None:
    key_b = Fernet.generate_key()
    assert lookup_hash("ana@example.com", context="email", key=key) != lookup_hash(
        "ana@example.com", context="email", key=key_b
    )


def test_decrypt_rejects_foreign_key(key: bytes) -> None:
    from passanorte_back.core.crypto import DecryptionError

    ciphertext = encrypt_value("ana@example.com", key)
    other = Fernet.generate_key()
    with pytest.raises(DecryptionError):
        decrypt_value(ciphertext, other)


def test_missing_key_raises_explicit_error() -> None:
    """A falsy key → explicit domain error, never a silent fallback."""
    with pytest.raises(CryptoKeyMissingError):
        encrypt_value("value", b"")
    with pytest.raises(CryptoKeyMissingError):
        lookup_hash("value", context="email", key=b"")
