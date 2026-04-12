# Artha

Personal Finance Advisory System — Phase 1: data aggregation and persistence.

## Quickstart

Prerequisites
- Python 3.12
- PostgreSQL (local or Docker)
- Redis (for notifications)
- Docker (optional, for infra)

Install dependencies

```bash
pip install -e ".[dev]"
```

Run the API (development)

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Start infrastructure (Postgres, Redis, metrics)

```bash
docker compose -f infra/docker-compose.yml up -d
```

Run tests

Unit tests (fast):

```bash
pytest tests/unit/
```

Integration tests (requires Docker infra):

```bash
pytest tests/integration/ -m integration
```

Database migrations

```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
```

Lint & format

```bash
ruff check .
ruff format .
```

## Overview

Artha is a Personal Finance Advisory System. Phase 1 implements a data aggregation
and persistence platform that ingests financial documents (bank statements,
credit card statements, mutual fund CAS) from multiple sources (Gmail, Zerodha,
manual upload), validates transactions, and persists them in PostgreSQL.

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Redis,
APScheduler, structlog + OpenTelemetry.

## Project layout

- `api/` — FastAPI app, routers, DI
- `services/` — ingestion pipeline, connectors, parsers, scheduler, storage
- `libs/` — shared domain types, schemas, money parsing, tax rules, telemetry
- `alembic/` — DB migrations
- `infra/` — Docker Compose and monitoring configs
- `tests/` — unit and integration tests

See [CLAUDE.md](CLAUDE.md) for an extended project guide.

## Core invariants

- **Money stored as paise (integer).** No floats — `libs/schemas/money.py` handles INR parsing.
- **Idempotency via `source_hash`.** Transaction upserts use `ON CONFLICT (source_hash) DO NOTHING`.
- **Document deduplication via `file_hash`.** SHA-256 of raw bytes prevents reprocessing.
- **Quarantine isolation.** Invalid records go to `transaction_quarantine`, not `transactions`.

## Ingestion pipeline (high level)

`services/ingestion/ingestion_service.py::IngestionService.run()` orchestrates:
1. Document dedup (`file_hash`)
2. Persist encrypted raw bytes to local filesystem
3. Parse bytes → `list[RawTransaction]` via parser factory
4. Run `ValidationPipeline` (schema → range → anomaly → locale)
5. Bulk upsert passed records (idempotent via `source_hash`)
6. Bulk insert quarantined records
7. Mark document parsed
8. Update `IngestionRun` stats
9. Publish Redis notifications

## Connectors & parsers

- Connectors: Gmail OAuth2, Zerodha Kite API, manual upload
- Parsers: bank statements, credit card statements, mutual fund CAS, manual parser

## Observability

Logging via `structlog`; tracing via OpenTelemetry with OTLP export to Jaeger.
Structured events use dot-notation keys (e.g., `ingestion.complete`).

## Ports (development)

- API: 8000
- PostgreSQL: 5432
- Redis: 6379
- Jaeger: 16686
- Prometheus: 9090
- Grafana: 3000

## Dev notes

Default local DB credentials used for convenience during development:

- user: `artha`
- password: `artha_secret`
- host: `localhost`
- db: `artha`

---

If you want, I can commit this file, run tests, or expand any section.
