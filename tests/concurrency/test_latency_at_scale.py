"""Phase 4: measure how the Postgres row-lock fix performs as concurrent
load increases. This produces the actual evidence for whether Redis is
needed later — not because the spec says so, but because these numbers
show it."""
# only 50 requests are in flight at once, regardless of total.

import time
import pytest

pytestmark = pytest.mark.slow
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

CONCURRENCY_LEVELS = [50, 100, 250, 500]
POOL_CAPACITY = 1_000_000  # effectively unlimited — isolates lock contention from sold-out rejections


def _percentile(sorted_values: list[float], pct: float) -> float:
    index = min(int(len(sorted_values) * pct), len(sorted_values) - 1)
    return sorted_values[index]


def test_latency_and_throughput_at_increasing_concurrency(client: TestClient) -> None:
    pool_id = client.post(
        "/pools", json={"name": "Load Test", "capacity": POOL_CAPACITY}
    ).json()["id"]

    print(
        f"\n{'Total reqs':>12} | {'Total time':>11} | {'Req/sec':>8} | "
        f"{'p50 (ms)':>9} | {'p95 (ms)':>9} | {'p99 (ms)':>9}"
    )
    print("-" * 74)

    for level in CONCURRENCY_LEVELS:
        latencies: list[float] = []

        def attempt(i: int) -> None:
            start = time.perf_counter()
            client.post(f"/pools/{pool_id}/reserve", json={"requester_id": f"user-{i}"})
            latencies.append((time.perf_counter() - start) * 1000)  # milliseconds

        start_total = time.perf_counter()
        with ThreadPoolExecutor(max_workers=50) as pool:
            list(pool.map(attempt, range(level)))
        total_time = time.perf_counter() - start_total

        latencies.sort()
        throughput = level / total_time

        print(
            f"{level:>12} | {total_time:>10.2f}s | {throughput:>8.1f} | "
            f"{_percentile(latencies, 0.50):>9.1f} | "
            f"{_percentile(latencies, 0.95):>9.1f} | "
            f"{_percentile(latencies, 0.99):>9.1f}"
        )