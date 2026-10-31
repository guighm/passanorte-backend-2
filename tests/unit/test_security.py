"""Unit: security primitives (research R1/R2; FR-005/FR-006, RNF10).

Password hashing (bcrypt, no plaintext), initial password generation and
the access-token round-trip (HS256, claims, expiry, forged signature).
"""

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from passanorte_back.core import security


def test_hash_password_stores_no_plaintext() -> None:
    """RNF10: the stored hash never contains the plaintext password."""
    hashed = security.hash_password("synthetic-test-password-1")
    assert "synthetic-test-password-1" not in hashed
    assert hashed.startswith("$2b$")  # bcrypt string format
    assert len(hashed) > 50


def test_hash_password_is_salted_and_verify_round_trip() -> None:
    """RNF10: same password hashes differently (salt) but verifies."""
    first = security.hash_password("synthetic-test-password-2")
    second = security.hash_password("synthetic-test-password-2")
    assert first != second  # salted
    assert security.verify_password("synthetic-test-password-2", first)
    assert security.verify_password("sythetic-wrong", first) is False


def test_generate_initial_password_is_random_and_long() -> None:
    """RF-010: system-generated initial password, secure random, <= 5 words."""
    first = security.generate_initial_password()
    second = security.generate_initial_password()
    assert first != second
    assert len(first) >= 12


def test_access_token_round_trip_and_claims() -> None:
    """FR-004/FR-006: the login pair issue is testable from primitives."""
    token = security.create_access_token(
        account_id=7,
        account_type="admin",
        role="admin",
        session_id=42,
        ttl=120,
        secret="test-only-synthetic-secret-not-real",
    )
    claims = security.decode_access_token(token, secret="test-only-synthetic-secret-not-real")
    assert claims["sub"] == "7"
    assert claims["account_type"] == "admin"
    assert claims["role"] == "admin"
    assert claims["sid"] == 42


def test_expired_token_is_rejected() -> None:
    """FR-005: expired sessions no longer grant access."""
    token = security.create_access_token(
        account_id=1,
        account_type="employee",
        role="employee",
        session_id=1,
        ttl=-10,  # already expired at issue
        secret="test-only-synthetic-secret-not-real",
    )
    with pytest.raises(pyjwt.InvalidTokenError):
        security.decode_access_token(token, secret="test-only-synthetic-secret-not-real")


def test_forged_signature_is_rejected() -> None:
    """RNF09: tokens signed with another secret are rejected."""
    now = datetime.now(UTC)
    forged = pyjwt.encode(
        {
            "sub": "1",
            "account_type": "admin",
            "role": "admin",
            "sid": 1,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        key="attacker-forge-key-32-bytes-long!!!!",
        algorithm=security.ALGORITHM,
    )
    with pytest.raises(pyjwt.InvalidTokenError):
        security.decode_access_token(forged, secret="test-only-synthetic-secret-not-real")


def test_refresh_token_is_hashed_not_stored() -> None:
    """R3: only the refresh-token hash is persisted (never the secret)."""
    token = security.generate_refresh_token()
    hashed = security.hash_refresh_token(token)
    assert token not in hashed
    assert security.hash_refresh_token(token) == hashed  # deterministic
    assert security.hash_refresh_token("other") != hashed
