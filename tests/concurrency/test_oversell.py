"""Fires many concurrent 'book now' requests at a small pool and checks
whether the system oversold it. This is the core proof-of-correctness
test for the whole project — everything else exists to make this pass
for real, not by accident."""
import pytest

pytestmark = pytest.mark.slow

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

CAPACITY = 50
CONCURRENT_REQUESTS = 300


def test_naive_reserve_oversells_under_concurrency(client: TestClient) -> None:
    pool_id = client.post(
        "/pools", json={"name": "Concurrency Test", "capacity": CAPACITY}
    ).json()["id"]

    def attempt(i: int) -> int:
        resp = client.post(
            f"/pools/{pool_id}/reserve", json={"requester_id": f"user-{i}"}
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(attempt, range(CONCURRENT_REQUESTS)))

    successful = results.count(201)

    print(f"\nRequests fired:    {CONCURRENT_REQUESTS}")
    print(f"Pool capacity:     {CAPACITY}")
    print(f"Successful (201):  {successful}")
    print(f"Oversold units:    {max(0, successful - CAPACITY)}")

    # This assertion is expected to FAIL right now — that failure is the proof
    # that the naive design (Phase 1) has a real business-critical bug.
    assert successful == CAPACITY, (
        f"Expected exactly {CAPACITY} successful reservations, got {successful}. "
        f"Oversold by {successful - CAPACITY}."
    )