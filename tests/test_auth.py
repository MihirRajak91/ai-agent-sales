
def test_protected_route_requires_valid_token(api_client):
    client, _db, _events = api_client

    unauthenticated = client.get("/api/leads")
    assert unauthenticated.status_code == 401

    token_response = client.post(
        "/auth/token",
        json={
            "org_id": "org1",
            "branch_id": "branch1",
            "user_id": "user1",
        },
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]

    authorised = client.get(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert authorised.status_code == 200
    assert authorised.json() == []


def test_invalid_token_is_rejected(api_client):
    client, _db, _events = api_client

    # Forge a token by truncating a valid one to simulate tampering.
    token_response = client.post(
        "/auth/token",
        json={
            "org_id": "org1",
            "branch_id": "branch1",
            "user_id": "user1",
        },
    )
    token = token_response.json()["access_token"]
    tampered_token = token[:-8] + "abcdef12"

    response = client.get(
        "/api/leads",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    assert response.status_code == 401
