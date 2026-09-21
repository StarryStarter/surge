# Surge

A distributed capacity-allocation engine: safely allocate finite resources (seats, tickets, inventory, slots) under extreme concurrent demand — no overselling, fair ordering, durable decisions.

> **Status: project scaffold only.** No allocation logic exists yet. Nothing in this repo currently claims any performance or correctness guarantee; each claim will be added only after a test or benchmark backs it up.

## Planned stack

Python + FastAPI, PostgreSQL, Redis (Lua), Postgres outbox + async workers, Nginx, Prometheus/Grafana, k6/Locust, GitHub Actions. Components are introduced one phase at a time, each only when the previous design is shown to fail.

## Prerequisites

- Python 3.12+

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # local config; .env is git-ignored

uvicorn app.main:app --reload      # http://127.0.0.1:8000
curl http://127.0.0.1:8000/healthz
```

Interactive API docs: http://127.0.0.1:8000/docs

## Tests

```bash
pytest
```

## Configuration

All configuration is via environment variables (see `.env.example`). Invalid values fail at startup. Secrets are never committed.

| Variable   | Default       | Meaning                                  |
| ---------- | ------------- | ---------------------------------------- |
| `APP_NAME` | `surge`       | Service name                             |
| `APP_ENV`  | `development` | `development` \| `test` \| `production`  |

## Layout

```
app/
  main.py, config.py     app factory, settings
  api/                   HTTP layer (routers, schemas)
  core/                  business logic — never imports FastAPI
    admission/ reservation/ pool/ fairness/ outbox/ reconciliation/ idempotency/
  workers/               background worker process entrypoints
demos/                   thin domain adapters (concert, railway, flash-sale)
tests/                   unit/ api/ integration/ concurrency/
loadtests/               k6/Locust scripts
docs/                    HLD, LLD, ADRs, benchmark report
```
