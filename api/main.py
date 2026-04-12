"""
Artha FastAPI application entrypoint.

Usage:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from api.routers.agent import router as agent_router
from api.routers.ingestion import ingestion_runs_router, router as ingestion_router
from libs.telemetry.logging import configure_logging
from libs.telemetry.tracing import configure_tracing
from services.scheduler.jobs import register_all_jobs
from services.scheduler.scheduler import get_scheduler

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────
    configure_logging()
    configure_tracing(service_name="artha")

    scheduler = get_scheduler()
    register_all_jobs()
    scheduler.start()
    log.info("artha.started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    log.info("artha.stopped")


app = FastAPI(
    title="Artha — Personal Finance Advisory System",
    description="Personal Finance Advisory System — Phase 2: Single-Agent Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ingestion_router)
app.include_router(ingestion_runs_router)
app.include_router(agent_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
