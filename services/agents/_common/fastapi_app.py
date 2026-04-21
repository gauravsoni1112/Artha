"""
FastAPI app factory for domain agents.

Each agent container calls make_agent_app() to get a ready-to-run FastAPI
application with:
  - POST /run      — accepts AgentRequest, returns AgentResponse
  - GET  /health   — returns {"status": "ok", "agent_id": ...}
  - Lifespan: self-registers with the registry on startup

Usage in each agent's main.py:
    from services.agents._common.fastapi_app import make_agent_app
    from services.agents.cashflow.agent import CashflowAgent

    app = make_agent_app(CashflowAgent)
"""

from __future__ import annotations

import hmac
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Type

import structlog
from fastapi import FastAPI, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.schemas.agent_envelope import AgentRequest, AgentResponse
from services.agents._common.base_agent import BaseAgent
from services.agents._common.self_register import self_register

log = structlog.get_logger(__name__)

_AGENT_SECRET: str = os.getenv("ARTHA_AGENT_SECRET", "dev-agent-secret-change-me")


def _verify_agent_secret(provided: str | None) -> None:
    """Raise 401 if the caller did not supply the correct agent secret."""
    if provided is None or not hmac.compare_digest(provided, _AGENT_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Artha-Agent-Secret",
        )


def make_agent_app(agent_class: Type[BaseAgent]) -> FastAPI:
    """
    Build and return a FastAPI application for *agent_class*.

    The engine / session factory is created once at startup; each request
    gets its own AsyncSession (no shared state between requests).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://artha:artha_secret@localhost:5432/artha",
        )
        engine = create_async_engine(db_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # Build the agent once — LLM clients and LangGraph compiled here.
        app.state.agent = agent_class(session_factory=session_factory)
        app.state.engine = engine

        # Self-register with the registry (retries internally)
        skip_register = os.getenv("SKIP_AGENT_REGISTRATION", "false").lower() == "true"
        if not skip_register:
            try:
                await self_register()
            except RuntimeError as exc:
                log.error("agent.startup.registration_failed", error=str(exc))
                # Don't crash the agent — it can still serve requests
                # even if the registry is temporarily unavailable.

        yield

        await engine.dispose()

    app = FastAPI(
        title=f"{agent_class.AGENT_ID} — Artha Domain Agent",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "agent_id": agent_class.AGENT_ID}

    @app.post("/run", response_model=AgentResponse)
    async def run(
        request: AgentRequest,
        x_artha_agent_secret: Annotated[str | None, Header(alias="X-Artha-Agent-Secret")] = None,
    ) -> AgentResponse:
        _verify_agent_secret(x_artha_agent_secret)

        agent: BaseAgent | None = getattr(app.state, "agent", None)
        if agent is None:
            raise HTTPException(status_code=503, detail="Agent not initialised")

        try:
            return await agent.run(request)
        except Exception as exc:
            log.error(
                "agent.run.error",
                agent_id=agent_class.AGENT_ID,
                trace_id=str(request.trace_id),
                error=str(exc),
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
