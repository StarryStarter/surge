import uuid

from fastapi.testclient import TestClient


def _create_pool(client: TestClient, capacity: int = 2) -> str:
    resp = client.post("/pools", json={"name": "GA", "capacity": capacity})
    assert resp.status_code == 201
    return resp.json()["id"]


def _reserve(client: TestClient, pool_id: str, requester_id: str, key: str | None = None):
    return client.post(
        f"/pools/{pool_id}/reserve",
        json={"requester_id": requester_id},
        headers={"Idempotency-Key": key or str(uuid.uuid4())},
    )


def test_create_pool_returns_full_capacity_available(client: TestClient) -> None:
    resp = client.post("/pools", json={"name": "GA", "capacity": 5})
    assert resp.status_code == 201
    body = resp.json()
    assert body["capacity"] == 5
    assert body["available"] == 5


def test_create_pool_rejects_non_positive_capacity(client: TestClient) -> None:
    resp = client.post("/pools", json={"name": "GA", "capacity": 0})
    assert resp.status_code == 422


def test_availability_for_unknown_pool_is_404(client: TestClient) -> None:
    resp = client.get(f"/pools/{uuid.uuid4()}/availability")
    assert resp.status_code == 404


def test_reserve_decrements_availability(client: TestClient) -> None:
    pool_id = _create_pool(client, capacity=2)
    resp = _reserve(client, pool_id, "alice")
    assert resp.status_code == 201
    assert resp.json()["status"] == "HELD"
    assert client.get(f"/pools/{pool_id}/availability").json()["available"] == 1


def test_reserve_on_sold_out_pool_is_409(client: TestClient) -> None:
    pool_id = _create_pool(client, capacity=1)
    first = _reserve(client, pool_id, "alice")
    assert first.status_code == 201  # now actually checked
    resp = _reserve(client, pool_id, "bob")
    assert resp.status_code == 409


def test_confirm_a_held_reservation(client: TestClient) -> None:
    pool_id = _create_pool(client)
    reservation_id = _reserve(client, pool_id, "alice").json()["id"]

    resp = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONFIRMED"


def test_confirming_twice_with_same_key_returns_same_result(client: TestClient) -> None:
    pool_id = _create_pool(client)
    reservation_id = _reserve(client, pool_id, "alice").json()["id"]
    confirm_key = str(uuid.uuid4())  # same key reused on purpose

    first = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"Idempotency-Key": confirm_key},
    )
    second = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"Idempotency-Key": confirm_key},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()  # replayed, not re-executed


def test_confirming_twice_with_different_keys_is_409(client: TestClient) -> None:
    pool_id = _create_pool(client)
    reservation_id = _reserve(client, pool_id, "alice").json()["id"]

    client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    resp = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers={"Idempotency-Key": str(uuid.uuid4())},  # a genuinely new attempt
    )
    assert resp.status_code == 409  # real business conflict, not a replay


def test_release_returns_the_unit_to_the_pool(client: TestClient) -> None:
    pool_id = _create_pool(client, capacity=1)
    reservation_id = _reserve(client, pool_id, "alice").json()["id"]

    resp = client.post(f"/reservations/{reservation_id}/release")
    assert resp.status_code == 200
    assert resp.json()["status"] == "RELEASED"
    assert client.get(f"/pools/{pool_id}/availability").json()["available"] == 1


def test_confirm_unknown_reservation_is_404(client: TestClient) -> None:
    resp = client.post(
        f"/reservations/{uuid.uuid4()}/confirm",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


def test_reserve_missing_idempotency_key_is_422(client: TestClient) -> None:
    pool_id = _create_pool(client)
    resp = client.post(f"/pools/{pool_id}/reserve", json={"requester_id": "alice"})
    assert resp.status_code == 422