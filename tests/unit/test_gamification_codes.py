"""Unit: redemption-code generation primitive (feature 009 — research R5).

``new_redemption_code`` is the CSPRNG primitive behind RF36/SC-004: codes are
128-bit `secrets.token_urlsafe(16)` values — URL-safe alphabet, unique under
volume, structurally independent from one another (no counter/identifier
leaks) and expiring nowhere (Q4: no expiration marker in the value). Pure
unit test — isolated from any app machinery.
"""

import re

from passanorte_back.modules.gamification.services.gamification import (
    new_redemption_code,
)

# token_urlsafe(16): 16 bytes → base64url without padding = 22 characters.
CODE_LENGTH = 22
URL_SAFE_ALPHABET = re.compile(r"^[A-Za-z0-9_-]+$")


def test_code_is_url_safe_and_22_characters_long() -> None:
    for _ in range(50):
        code = new_redemption_code()
        assert isinstance(code, str)
        assert len(code) == CODE_LENGTH
        assert URL_SAFE_ALPHABET.fullmatch(code)


def test_codes_are_unique_across_a_1_000_code_batch() -> None:
    codes = {new_redemption_code() for _ in range(1_000)}
    assert len(codes) == 1_000


def test_consecutive_codes_share_no_structural_relationship() -> None:
    """No derivability from counters or identifiers (SC-004).

    Consecutive values must differ at multiple independent positions
    (a counter would share a nearly identical prefix) and must never be
    an equal/padded variant of each other.
    """
    previous = new_redemption_code()
    for _ in range(30):
        current = new_redemption_code()
        assert current != previous
        differing = sum(1 for a, b in zip(previous, current, strict=True) if a != b)
        assert differing >= 8, (previous, current)
        assert not previous.startswith(current[:1] * 6) or not current.startswith(previous[:1] * 6)
        previous = current


def test_codes_carry_no_expiration_semantics() -> None:
    """Q4 — no expiration in v1: the primitive accepts no expiry argument
    at all (codes stay valid until honored; would raise TypeError otherwise)."""
    try:
        new_redemption_code(expires_in_days=30)  # type: ignore[call-arg]
    except TypeError:
        pass
    else:
        raise AssertionError("new_redemption_code must not accept expiration arguments")
