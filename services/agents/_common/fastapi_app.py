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

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Type

import structlog
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.schemas.agent_envelope import AgentRequest, AgentResponse
from services.agents._common.base_agent import BaseAgent
from services.agents._common.self_register import self_register

log = structlog.get_logger(__name__)


def make_agent_app(agent_class: Type[BaseAgent]) -> FastAPI:
    """
    Build and return a FastAPI application for *agent_class*.

    The engine / session factory is created once at startup; each request
    gets its own AsyncSession (no shared state between requests).
    """

    engine_holder: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://artha:artha_secret@localhost:5432/artha",
        )
        engine = create_async_engine(db_url, pool_pre_ping=True)
        engine_holder["engine"] = engine
        engine_holder["session_factory"] = async_sessionmaker(
            engine, expire_on_commit=False
        )

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
    async def run(request: AgentRequest) -> AgentResponse:
        session_factory = engine_holder.get("session_factory")
        if session_factory is None:
            raise HTTPException(status_code=503, detail="DB session not initialised")

        async with session_factory() as session:
            agent = agent_class(session=session)
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
