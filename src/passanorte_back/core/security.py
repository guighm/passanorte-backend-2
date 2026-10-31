"""Security primitives shared by every module (research R1/R2/R3).

- Password hashing with bcrypt (RNF10): ``hash_password``/``verify_password``.
- Access-token (JWT HS256) encode/decode with the claims this feature needs
  (``sub``, ``account_type``, ``role``, ``sid``, ``exp``/``iat``) — RNF09.
- Opaque refresh-token generation + hashing (only the hash is persisted,
  research R3).

The FastAPI dependencies that use these primitives (``get_current_user``,
``require_admin``) live in ``modules/auth/services/security.py`` (public
interface of the auth module; the boundary checker allows only cross-module
imports from ``services``).
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import bcrypt
import jwt as pyjwt

ALGORITHM: Final = "HS256"
BCRYPT_ROUNDS: Final = 12
MIN_GENERATED_PASSWORD_LENGTH: Final = 16


def hash_password(password: str) -> str:
    """Hash a password with bcrypt (salt included in the hash — RNF10)."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_initial_password() -> str:
    """Secure random initial password (system-generated — clar. Q3-s4)."""
    while True:
        password = secrets.token_urlsafe(16)
        if len(password) >= MIN_GENERATED_PASSWORD_LENGTH:
            return password


def generate_refresh_token() -> str:
    """Opaque refresh credential (research R3): high-entropy URL-safe token."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(refresh_token: str) -> str:
    """SHA-256 of an opaque refresh token (only the hash is persisted)."""
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    account_id: int,
    account_type: str,
    role: str,
    session_id: int,
    ttl: int,
    secret: str,
) -> str:
    """Encode a short-lived access token (JWT HS256).

    ``sid`` binds the token to its ``auth_sessions`` row (used for logout
    and single-use refresh). ``exp``/``iat`` in UTC.
    """
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(account_id),
        "account_type": account_type,
        "role": role,
        "sid": session_id,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return pyjwt.encode(claims, key=secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    """Decode and verify an access token.

    Raises ``jwt.InvalidTokenError`` (including expired/forged) — callers
    translate that into HTTP 401 (FR-015).
    """
    return pyjwt.decode(token, key=secret, algorithms=[ALGORITHM])
