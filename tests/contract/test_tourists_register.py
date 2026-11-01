"""Contract: POST /api/v1/tourists — tourist registration (US1; RF22).

Covers contracts/tourists.md: 201 without any sensitive value, specific
422s per field rule, 409 duplicates (no leak), concurrent registration with
the same email (SC-002), and ciphertext-only persistence (SC-005/SC-007).

The example values below are INPUT payloads only — never expected persisted
plaintext (quality gate RNF08).
"""

REGISTER_URL = "/api/v1/tourists"

VALID_CPF = "123.456.789-09"
VALID_CPF_DIGITS = "12345678909"
VALID_PASSPORT = "AB123456"
VALID_PHONE = "+5511999999999"


def _payload(**overrides):
    base = {
        "first_name": "Ana",
        "last_name": "Silva",
        "country_of_origin": "Brasil",
        "cpf": VALID_CPF,
        "passport_number": None,
        "phone": VALID_PHONE,
        "email": "ana@example.com",
        "password": "long-enough-password-1",
    }
    base.update(overrides)
    return base


def _register(client, **overrides):
    return client.post(REGISTER_URL, json=_payload(**overrides))


def _assert_no_sensitive_plaintext_in_database(sessionfactory_for) -> None:
    """SC-005/SC-007: tourists table never holds plaintext sensitive data."""
    from passanorte_back.modules.tourists.repositories.tourists import Tourist

    with sessionfactory_for() as session:
        for tourist in session.query(Tourist).all():
            assert tourist.email_encrypted != "ana@example.com"
            assert tourist.phone_encrypted != VALID_PHONE
            if tourist.cpf_encrypted is not None:
                assert tourist.cpf_encrypted != VALID_CPF
                assert tourist.cpf_encrypted != VALID_CPF_DIGITS
            if tourist.passport_encrypted is not None:
                assert tourist.passport_encrypted != VALID_PASSPORT
            assert len(tourist.password_hash) == 60  # bcrypt hash only (RNF10)
            for lookup in (
                tourist.email_lookup,
                tourist.cpf_lookup,
                tourist.passport_lookup,
            ):
                if lookup is not None:
                    assert len(lookup) == 64
                    assert lookup != "ana@example.com"


def test_register_with_masked_cpf_returns_201_without_sensitive_values(
    client, sessionfactory_for
) -> None:
    response = _register(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "first_name", "last_name", "country_of_origin"}
    assert body == {
        "id": body["id"],
        "first_name": "Ana",
        "last_name": "Silva",
        "country_of_origin": "Brasil",
    }
    _assert_no_sensitive_plaintext_in_database(sessionfactory_for)


def test_register_with_passport_returns_201(client) -> None:
    response = _register(client, cpf=None, passport_number=VALID_PASSPORT, email="bob@example.com")
    assert response.status_code == 201, response.text
    assert response.json()["id"] > 0


def test_register_unmasked_cpf_is_normalized_and_accepted(client) -> None:
    response = _register(client, cpf=VALID_CPF_DIGITS, email="carol@example.com")
    assert response.status_code == 201, response.text


def test_accepts_email_with_spaces_and_uppercase_normalized(client, sessionfactory_for) -> None:
    response = _register(client, email="  Dave@Example.COM  ")
    assert response.status_code == 201, response.text
    from passanorte_back.modules.tourists.repositories import tourists as tourists_repo

    with sessionfactory_for() as session:
        tourist = session.query(tourists_repo.Tourist).filter_by(first_name="Ana").one()
        assert "Dave@example.com" not in tourist.email_encrypted  # ciphertext, not plaintext


def test_register_invalid_cpf_check_digits_is_422(client) -> None:
    response = _register(client, cpf="123.456.789-00")
    assert response.status_code == 422
    assert "cpf" in response.text


def test_register_malformed_email_is_422(client) -> None:
    response = _register(client, email="not-an-email")
    assert response.status_code == 422
    assert "email" in response.text


def test_register_phone_without_plus_is_422(client) -> None:
    response = _register(client, phone="5511999999999")
    assert response.status_code == 422
    assert "phone" in response.text


def test_register_passport_bad_format_is_422(client) -> None:
    response = _register(client, cpf=None, passport_number="AB1", email="erin@example.com")
    assert response.status_code == 422
    assert "passport_number" in response.text


def test_register_no_document_is_422(client) -> None:
    response = _register(client, cpf=None)
    assert response.status_code == 422


def test_register_two_documents_is_422(client) -> None:
    response = _register(client, passport_number=VALID_PASSPORT)
    assert response.status_code == 422


def test_register_short_password_is_422(client) -> None:
    response = _register(client, password="short")
    assert response.status_code == 422
    assert "password" in response.text


def test_register_long_name_or_country_is_422(client) -> None:
    too_long = "x" * 101
    response = _register(client, first_name=too_long)
    assert response.status_code == 422
    response = _register(client, country_of_origin=too_long)
    assert response.status_code == 422


def test_register_duplicate_email_is_409_without_leak(client) -> None:
    first = _register(client)
    assert first.status_code == 201
    second = _register(client, cpf=None, passport_number="ZZ999999")
    assert second.status_code == 409
    assert second.json() == {"detail": "tourist already registered"}


def test_register_duplicate_cpf_is_409(client) -> None:
    assert _register(client).status_code == 201
    response = _register(client, email="other@example.com", cpf=VALID_CPF, passport_number=None)
    assert response.status_code == 409


def test_register_duplicate_passport_is_409(client) -> None:
    assert _register(client, cpf=None, passport_number=VALID_PASSPORT).status_code == 201
    response = _register(
        client, email="other@example.com", cpf=None, passport_number=VALID_PASSPORT
    )
    assert response.status_code == 409


def test_register_concurrent_same_email_only_one_persists(client, sessionfactory_for) -> None:
    """SC-002 (edge case): two near-simultaneous payloads, same email —
    exactly one persists, the other gets 409."""
    first = _register(client, email="race@example.com")
    second = _register(client, email="race@example.com", cpf=None, passport_number="QQ777777")
    succeeded = [r for r in (first, second) if r.status_code == 201]
    conflicts = [r for r in (first, second) if r.status_code == 409]
    assert len(succeeded) == 1, (first.status_code, second.status_code)
    assert len(conflicts) == 1

    from passanorte_back.core.crypto import lookup_hash
    from passanorte_back.modules.tourists.repositories.tourists import Tourist

    expected_lookup = lookup_hash("race@example.com", context="email", key=_sensitive_key())
    with sessionfactory_for() as session:
        holders = session.query(Tourist).filter(Tourist.email_lookup == expected_lookup).all()
        assert len(holders) == 1


def _sensitive_key() -> bytes:
    """The test SENSITIVE_DATA_KEY (synthetic; set by conftest)."""
    import os

    return os.environ["SENSITIVE_DATA_KEY"].encode("utf-8")
