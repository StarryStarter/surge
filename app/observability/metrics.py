from prometheus_client import Counter, Gauge

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
OVERSOLD_DETECTED = Counter(
    "surge_oversold_detected_total", "Pools with more active reservations than capacity"
)
RATE_LIMITED = Counter(
    "surge_rate_limited_total", "Reserve requests rejected by the rate limiter"
)