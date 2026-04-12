"""
FastAPI dependency injection helpers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from api.database import AsyncSessionLocal
from services.ingestion.ingestion_service import IngestionService
from services.storage.file_store import FileStore
from services.storage.notification import NotificationClient
from services.validation.pipeline import ValidationPipeline
from services.validation.pipeline import InMemorySpendHistory


@asynccontextmanager
async def get_ingestion_service() -> AsyncGenerator[IngestionService, None]:
    """
    Async context manager that creates a fully wired IngestionService.

    In production, AnomalyDetector should use a PostgresSpendHistory that
    queries the transactions table. For now we use InMemorySpendHistory
    (Phase 2 will replace this with a DB-backed implementation).
    """
    async with AsyncSessionLocal() as session:
        async with NotificationClient() as notifications:
            pipeline = ValidationPipeline(spend_history=InMemorySpendHistory())
            file_store = FileStore()
            svc = IngestionService(
                session=session,
                pipeline=pipeline,
                file_store=file_store,
                notifications=notifications,
            )
            yield svc
