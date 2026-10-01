import uuid

from fastapi.testclient import TestClient

from app.core.fairness.rate_limiter import RateLimiter

def _reserve(client: TestClient, pool_id: str, who: str):  # type: ignore[no-untyped-def]
    return client.post(
        f"/pools/{pool_id}/reserve",
        json={"requester_id": who},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

def test_reserve_is_rate_limited_per_requester(client: TestClient) -> None:
    # Tighten the limit for this test only.
    client.app.state.rate_limiter = RateLimiter(  # type: ignore[attr-defined]
        client.app.state.redis, limit=2, window_seconds=60  # type: ignore[attr-defined]
    )
    pool_id = client.post("/pools", json={"name": "GA", "capacity": 10}).json()["id"]

    assert _reserve(client, pool_id, "mallory").status_code == 201
    assert _reserve(client, pool_id, "mallory").status_code == 201
    blocked = _reserve(client, pool_id, "mallory")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1

    assert _reserve(client, pool_id, "alice").status_code == 201  # unaffected