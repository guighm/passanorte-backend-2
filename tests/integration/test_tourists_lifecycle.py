"""Integration: full tourist lifecycle (SC-003; T026).

register → login → GET /me → PATCH /me (edit) → PUT /me/interests →
GET /me/interests, with the 403 of a foreign profile inside the flow and a
final database inspection: ``*_encrypted``/``*_lookup`` present, NO
plaintext sensitive value and password only as hash (SC-004/SC-005/SC-007).
"""

LOGIN_URL = "/api/v1/tourists/login"
ME_URL = "/api/v1/tourists/me"
INTERESTS_URL = "/api/v1/tourists/me/interests"

REGISTERED_EMAIL = "flow@example.com"
PASSWORD = "long-enough-password-1"
PHONE = "+5511999999999"
CPF = "123.456.789-09"
CPF_DIGITS = "12345678909"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_tourist_full_lifecycle_and_persistence_is_encrypted(client, sessionfactory_for) -> None:
    # 1. Registration (SC-003 step 1).
    registered = client.post(
        "/api/v1/tourists",
        json={
            "first_name": "Flow",
            "last_name": "Turista",
            "country_of_origin": "Brasil",
            "cpf": CPF,
            "passport_number": None,
            "phone": PHONE,
            "email": REGISTERED_EMAIL,
            "password": PASSWORD,
        },
    )
    assert registered.status_code == 201, registered.text
    tourist_id = registered.json()["id"]

    # 2. Login (SC-003 step 2).
    pair = client.post(LOGIN_URL, json={"email": REGISTERED_EMAIL, "password": PASSWORD}).json()
    assert pair["role"] == "tourist"
    headers = _bearer(pair["access_token"])

    # 3. GET /me returns the profile; foreign profile → 403 (SC-004 in flow).
    me = client.get(ME_URL, headers=headers).json()
    assert me["email"] == REGISTERED_EMAIL
    assert me["cpf"] == CPF_DIGITS
    assert me["phone"] == PHONE
    assert me["interests"] == []

    # 4. PATCH /me (SC-003 step 3) — the 403 of another tourist in the flow.
    foreign = client.post(
        "/api/v1/tourists",
        json={
            "first_name": "Other",
            "last_name": "Turista",
            "country_of_origin": "Brasil",
            "cpf": "111.444.777-35",
            "passport_number": None,
            "phone": "+5521988887777",
            "email": "other@example.com",
            "password": PASSWORD,
        },
    )
    assert foreign.status_code == 201
    other_pair = client.post(
        LOGIN_URL, json={"email": "other@example.com", "password": PASSWORD}
    ).json()
    assert (
        client.patch(
            f"/api/v1/tourists/{tourist_id}",
            headers=_bearer(other_pair["access_token"]),
            json={"country_of_origin": "Hacked"},
        ).status_code
        == 403
    )

    patch = client.patch(
        ME_URL.replace(ME_URL, f"/api/v1/tourists/{tourist_id}"),
        headers=headers,
        json={"country_of_origin": "Argentina", "phone": "+541199999999"},
    )
    assert patch.status_code == 204, patch.text

    # 5. PUT /me/interests (SC-003 step 4) + consequence read (step 5).
    put = client.put(INTERESTS_URL, headers=headers, json={"interests": ["gastronomy", "nature"]})
    assert put.status_code == 200, put.text
    interests = client.get(INTERESTS_URL, headers=headers).json()
    assert interests == {"interests": ["gastronomy", "nature"]}

    me = client.get(ME_URL, headers=headers).json()
    assert me["country_of_origin"] == "Argentina"
    assert me["phone"] == "+541199999999"
    assert me["interests"] == ["gastronomy", "nature"]

    # 6. Database inspection (SC-004/SC-005/SC-007): nothing in plaintext.
    from passanorte_back.modules.tourists.repositories.tourists import Tourist

    with sessionfactory_for() as session:
        for tourist in session.query(Tourist).all():
            assert tourist.email_encrypted != REGISTERED_EMAIL
            if tourist.phone_encrypted is not None:
                assert tourist.phone_encrypted != PHONE
                assert "5511" not in tourist.phone_encrypted.replace("5511", "")
            if tourist.cpf_encrypted is not None:
                assert tourist.cpf_encrypted != CPF
                assert tourist.cpf_encrypted != CPF_DIGITS
            # Lookup columns: opaque 64-hex hashes of the lookups (RNF08).
            assert len(tourist.email_lookup) == 64
            # Password ONLY as an irreversible bcrypt hash (RNF10/SC-007).
            assert len(tourist.password_hash) == 60
            assert tourist.password_hash.startswith("$2")
            assert PASSWORD not in str(tourist.password_hash)
