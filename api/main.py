"""
Artha FastAPI application entrypoint.

Usage:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

import os

from dotenv import load_dotenv

# Load .env before any module reads os.getenv() — a no-op when env vars are
# already injected by Docker Compose (load_dotenv does not override existing vars).
load_dotenv()

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.database import AsyncSessionLocal
from api.rate_limit import limiter
from api.routers.accounts import router as accounts_router
from api.routers.admin import router as admin_router
from api.routers.agent import router as agent_router
from api.routers.agent_router import router as domain_router
from api.routers.auth import router as auth_router
from api.routers.goals import router as goals_router
from api.routers.holdings import router as holdings_router
from api.routers.ingestion import ingestion_runs_router, router as ingestion_router
from api.routers.net_worth import router as net_worth_router
from api.routers.orchestrator import router as orchestrator_router
from api.routers.owners import router as owners_router
from api.routers.profile import router as profile_router
from api.routers.registry import router as registry_router
from api.routers.static_data import router as static_data_router
from api.routers.tax_data import router as tax_data_router
from api.routers.transactions import router as transactions_router
from libs.telemetry.langfuse_handler import flush as lf_flush
from libs.telemetry.logging import configure_logging
from libs.telemetry.tracing import configure_tracing
from services.orchestrator.breaker import BreakerConfig, InMemoryBreakerStore
from services.orchestrator.cache import AgentResponseCache
from services.orchestrator.registry import AgentRegistryCache, schedule_registry_refresh
from services.scheduler.jobs import register_all_jobs
from services.scheduler.scheduler import get_scheduler

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────
    configure_logging()
    configure_tracing(service_name="artha")

    # Orchestrator singletons
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = aioredis.from_url(redis_url, decode_responses=False)
    app.state.registry = AgentRegistryCache(session_factory=AsyncSessionLocal)
    app.state.breaker = InMemoryBreakerStore(BreakerConfig())
    app.state.response_cache = AgentResponseCache(redis_client=redis_client)

    try:
        await app.state.registry.refresh()
    except Exception as exc:
        log.warning("orchestrator.registry_initial_refresh_failed", error=str(exc))

    scheduler = get_scheduler()
    register_all_jobs()
    schedule_registry_refresh(scheduler, app.state.registry, interval_seconds=60)
    scheduler.start()
    log.info("artha.started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    await redis_client.aclose()
    lf_flush()  # drain any buffered Langfuse events before the process exits
    log.info("artha.stopped")


app = FastAPI(
    title="Artha — Personal Finance Advisory System",
    description="Personal Finance Advisory System — Phase 2: Single-Agent Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────
_cors_origins = os.getenv(
    "ARTHA_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiting ────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)
app.include_router(owners_router)
app.include_router(accounts_router)
app.include_router(goals_router)
app.include_router(holdings_router)
app.include_router(net_worth_router)
app.include_router(tax_data_router)
app.include_router(profile_router)
app.include_router(transactions_router)
app.include_router(static_data_router)
app.include_router(admin_router)
app.include_router(ingestion_router)
app.include_router(ingestion_runs_router)
app.include_router(agent_router)
app.include_router(registry_router)
app.include_router(domain_router)
app.include_router(orchestrator_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
