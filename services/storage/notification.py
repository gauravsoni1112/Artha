"""
NotificationClient — Redis pub/sub for ingestion status events.

Channels:
  artha:ingestion:status   → published after every document is processed
  artha:quarantine:alerts  → published when any record is quarantined

Message format (JSON):
  ingestion:status  { "run_id": "...", "passed": N, "quarantined": N, "document_id": "..." }
  quarantine:alerts { "count": N, "document_id": "..." }

Consumers (future agents/UI) subscribe to these channels to receive
real-time notifications without polling the database.
"""

from __future__ import annotations

import json
import os
import uuid

import structlog

log = structlog.get_logger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_CHANNEL_STATUS = "artha:ingestion:status"
_CHANNEL_QUARANTINE = "artha:quarantine:alerts"


class NotificationClient:
    """
    Async Redis pub/sub publisher.

    Uses redis-py's async client. Call connect() before use (or use as async context manager).
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._url = redis_url or _REDIS_URL
        self._client = None

    async def connect(self) -> None:
        import redis.asyncio as aioredis
        self._client = aioredis.from_url(self._url, decode_responses=True)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "NotificationClient":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect()

    async def publish_ingestion_status(
        self,
        run_id: uuid.UUID,
        passed: int,
        quarantined: int,
        document_id: uuid.UUID,
    ) -> None:
        payload = json.dumps(
            {
                "run_id": str(run_id),
                "passed": passed,
                "quarantined": quarantined,
                "document_id": str(document_id),
            }
        )
        await self._publish(_CHANNEL_STATUS, payload)

    async def publish_quarantine_alert(
        self,
        count: int,
        document_id: uuid.UUID,
    ) -> None:
        payload = json.dumps({"count": count, "document_id": str(document_id)})
        await self._publish(_CHANNEL_QUARANTINE, payload)

    async def _publish(self, channel: str, payload: str) -> None:
        if self._client is None:
            log.warning("notification.not_connected", channel=channel)
            return
        try:
            await self._client.publish(channel, payload)
            log.debug("notification.published", channel=channel)
        except Exception as exc:
            # Notifications are best-effort — never block ingestion on Redis failure
            log.warning("notification.publish_failed", channel=channel, error=str(exc))
