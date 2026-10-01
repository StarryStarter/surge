"""Fire concurrent reserve requests at the stack and verify nothing oversold.

    python loadtest/oversell.py                      # 300 requests, capacity 50
    python loadtest/oversell.py --requests 5000 --capacity 500 --concurrency 100
    python loadtest/oversell.py --requests 20000 --capacity 500 --fill-first
        # sells the pool out first, then measures only the traffic after sell-out
"""

import argparse
import asyncio
import statistics
import sys
import time
import uuid

import httpx

def _percentiles(values: list[float]) -> str:
    if len(values) < 2:
        return "n/a"
    cuts = statistics.quantiles(values, n=100)
    return f"{cuts[49] * 1000:.0f} / {cuts[94] * 1000:.0f} / {cuts[98] * 1000:.0f} ms"

async def burst(
    client: httpx.AsyncClient,
    pool_id: str,
    count: int,
    first_index: int,
    concurrency: int,
) -> tuple[dict[object, list[float]], float]:
    """Send `count` reserve requests; return latencies by status and elapsed time."""
    gate = asyncio.Semaphore(concurrency)
    by_status: dict[object, list[float]] = {}

    async def one(i: int) -> None:
        async with gate:
            started = time.perf_counter()
            try:
                resp = await client.post(
                    f"/pools/{pool_id}/reserve",
                    json={"requester_id": f"user-{first_index + i}"},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )
                code: object = resp.status_code
            except httpx.HTTPError as exc:
                code = type(exc).__name__
            by_status.setdefault(code, []).append(time.perf_counter() - started)

    began = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(count)))
    return by_status, time.perf_counter() - began

async def run(args: argparse.Namespace) -> int:
    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    async with httpx.AsyncClient(
        base_url=args.base_url, limits=limits, timeout=60
    ) as client:
        created = await client.post(
            "/pools", json={"name": "loadtest", "capacity": args.capacity}
        )
        created.raise_for_status()
        pool_id = created.json()["id"]

        filled = 0
        if args.fill_first:
            fill_status, _ = await burst(
                client, pool_id, args.capacity, 0, args.concurrency
            )
            filled = len(fill_status.get(201, []))
            print(f"Fill phase:         {filled} of {args.capacity} units sold")

        by_status, elapsed = await burst(
            client, pool_id, args.requests, args.capacity if args.fill_first else 0,
            args.concurrency,
        )
        availability = await client.get(f"/pools/{pool_id}/availability")
        available = availability.json()["available"]

    statuses = {code: len(v) for code, v in by_status.items()}
    successes = statuses.get(201, 0) + filled
    total_sent = args.requests + (args.capacity if args.fill_first else 0)
    expected = min(total_sent, args.capacity)
    everything = [x for v in by_status.values() for x in v]

    label = "measured phase" if args.fill_first else "all requests"
    print(f"Requests fired:     {args.requests} ({label})")
    print(f"Pool capacity:      {args.capacity}")
    print(f"Status counts:      {dict(sorted(statuses.items(), key=str))}")
    print(f"Successful (201):   {successes} (including fill phase)")
    print(f"Oversold units:     {max(successes - args.capacity, 0)}")
    print(f"Left in pool:       {available}")
    print(f"Elapsed:            {elapsed:.2f}s  ({args.requests / elapsed:,.0f} req/s)")
    print(f"Latency p50/p95/p99 (all):  {_percentiles(everything)}")
    for code in (201, 409):
        if code in by_status:
            print(f"Latency p50/p95/p99 ({code}): {_percentiles(by_status[code])}")

    ok = successes == expected and available == max(args.capacity - successes, 0)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--capacity", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=300)
    parser.add_argument(
        "--fill-first",
        action="store_true",
        help="sell the pool out first, then measure only the traffic after sell-out",
    )
    sys.exit(asyncio.run(run(parser.parse_args())))

if __name__ == "__main__":
    main()