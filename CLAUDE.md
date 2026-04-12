# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Artha is a Personal Finance Advisory System. The current implementation (Phase 1) is a data aggregation and persistence platform that ingests financial documents (bank statements, credit card statements, mutual fund CAS) from multiple sources (Gmail, Zerodha, manual upload), validates transactions, and persists them in PostgreSQL.

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, Redis 7, APScheduler, structlog + OpenTelemetry.

## Commands

### Install dependencies
```bash
pip install -e ".[dev]"
```

### Run the API server
```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Run tests
```bash
# All unit tests (no Docker required)
pytest tests/unit/

# Single test file
pytest tests/unit/money/test_parser.py

# Single test
pytest tests/unit/money/test_parser.py::test_parse_inr_lakhs

# Integration tests (requires Docker with Postgres running)
pytest tests/integration/ -m integration
```

### Start infrastructure services
```bash
docker compose -f infra/docker-compose.yml up -d
```

### Database migrations (requires running Postgres)
```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Lint
```bash
ruff check .
ruff format .
```

## Architecture

### Directory layout
```
api/          — FastAPI routers and dependency injection
services/     — Business logic (ingestion, validation, storage, scheduler)
libs/         — Shared domain types (ORM models, enums, money, tax rules, telemetry)
alembic/      — Database migrations
infra/        — Docker Compose, Prometheus config
tests/
  unit/       — No external dependencies; runs without Docker
  integration/— Requires running Postgres; marked @pytest.mark.integration
```

### Core invariants
- **Money is always stored as paise (integer).** Never use floats for amounts. `libs/schemas/money.py` handles INR parsing including Indian number format (₹1,00,000 → 10000000 paise).
- **Idempotency via `source_hash`.** Transaction upserts use `ON CONFLICT (source_hash) DO NOTHING`. Re-ingesting the same document is safe.
- **Document deduplication via `file_hash`** (SHA-256 of raw bytes) before any processing.
- **Quarantine isolation.** Records that fail validation never reach the `transactions` table — they go to `transaction_quarantine` only.

### Ingestion pipeline (9 steps)
`services/ingestion/ingestion_service.py::IngestionService.run()` orchestrates:
1. Document dedup (file_hash)
2. Persist encrypted raw bytes to local filesystem
3. Parse bytes → `list[RawTransaction]` via parser factory
4. Run `ValidationPipeline` (4 stages: schema → range → anomaly → locale)
5. Bulk upsert passed records (idempotent via source_hash)
6. Bulk insert quarantined records
7. Mark document parsed
8. Update `IngestionRun` stats
9. Publish Redis notifications

### Service composition
`IngestionService` takes its dependencies via constructor injection:
- `AsyncSession` (PostgreSQL)
- `ValidationPipeline`
- `FileStore` (encrypted local storage, Fernet)
- `NotificationClient` (Redis pub/sub)

### ORM models (`libs/schemas/db_models.py`)
Key tables: `owners`, `accounts`, `transactions`, `transaction_quarantine`, `documents`, `ingestion_runs`.

`fiscal_year` on transactions is computed at insert time using `libs/tax_rules/fiscal_year.py` (Indian April–March fiscal year).

### Connectors and parsers
- `services/ingestion/connectors/` — Gmail OAuth2, Zerodha Kite API, manual upload
- `services/ingestion/parsers/` — bank statement, credit card statement, MF CAS; selected by `parsers/factory.py` based on `doc_type`

### Infrastructure ports
| Service    | Port  |
|------------|-------|
| PostgreSQL | 5432  |
| Redis      | 6379  |
| API        | 8000  |
| Jaeger UI  | 16686 |
| Prometheus | 9090  |
| Grafana    | 3000  |

Default DB credentials (local dev): `artha / artha_secret @ localhost:5432/artha`

### Observability
`libs/telemetry/logging.py` configures structlog. `libs/telemetry/tracing.py` configures OTLP export to Jaeger. All structured log events use dot-notation keys (e.g., `ingestion.complete`). Use `start_span()` for manual tracing spans.
