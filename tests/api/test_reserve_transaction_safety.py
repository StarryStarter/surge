"""Locks in the Phase 3 fix: the lock-based reserve() should never oversell,
never go negative, and should hold up under repeated concurrent hits."""

from concurrent.futures import ThreadPoolExecutor

import uuid
from fastapi.testclient import TestClient


def test_sold_out_pool_never_goes_negative(client: TestClient) -> None:
    pool_id = client.post("/pools", json={"name": "GA", "capacity": 1}).json()["id"]

    first = client.post(
        f"/pools/{pool_id}/reserve",
        json={"requester_id": "alice"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    second = client.post(
        f"/pools/{pool_id}/reserve",
        json={"requester_id": "bob"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert first.status_code == 201
    assert second.status_code == 409

    availability = client.get(f"/pools/{pool_id}/availability").json()
    assert availability["available"] == 0


def test_small_scale_concurrency_regression(client: TestClient) -> None:
    capacity = 5
    pool_id = client.post("/pools", json={"name": "GA", "capacity": capacity}).json()["id"]

    def attempt(i: int) -> int:
        resp = client.post(
            f"/pools/{pool_id}/reserve",
            json={"requester_id": f"user-{i}"},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(20)))

    assert results.count(201) == capacity