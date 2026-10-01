from prometheus_client import Counter, Gauge
from prometheus_client import Counter, Gauge, Histogram

OUTBOX_EVENTS = Counter(
    "surge_outbox_events_total", "Outbox events handled", ["result"]
)
HOLDS_EXPIRED = Counter("surge_holds_expired_total", "Reservation holds expired")
RECONCILE_HEALS = Counter(
    "surge_reconcile_heals_total", "Redis counters repaired", ["kind"]
)
RECONCILE_DRIFTED_POOLS = Gauge(
    "surge_reconcile_drifted_pools", "Pools whose Redis counter disagreed with Postgres"
)
OVERSOLD_POOLS = Gauge(
    "surge_oversold_pools",
    "Pools with more active reservations than capacity, as of the last pass",
)
RATE_LIMITED = Counter(
    "surge_rate_limited_total", "Reserve requests rejected by the rate limiter"
)
HTTP_REQUESTS = Counter(
    "surge_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "surge_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)