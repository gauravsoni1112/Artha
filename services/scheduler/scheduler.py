"""
APScheduler setup for Artha.

Uses AsyncIOScheduler (in-process, no extra worker processes).
Redis is used as the job store so jobs survive restarts.

Usage:
    from services.scheduler.scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.start()
    # Register jobs:
    scheduler.add_job(my_job, "cron", hour=6, minute=0, id="gmail_ingest")
"""

import os

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import structlog

log = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return the singleton AsyncIOScheduler instance."""
    global _scheduler
    if _scheduler is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        # Parse host/port from URL for APScheduler RedisJobStore
        # redis://localhost:6379/0 → host=localhost, port=6379, db=0
        import re
        m = re.match(r"redis://([^:]+):(\d+)/(\d+)", redis_url)
        if m:
            host, port, db = m.group(1), int(m.group(2)), int(m.group(3))
        else:
            host, port, db = "localhost", 6379, 1

        jobstores = {
            "default": RedisJobStore(host=host, port=port, db=db),
        }
        executors = {
            "default": AsyncIOExecutor(),
        }
        job_defaults = {
            "coalesce": True,       # run only once if missed multiple times
            "max_instances": 1,     # never run the same job concurrently
            "misfire_grace_time": 3600,  # tolerate up to 1hr of missed time
        }
        _scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )
        log.info("scheduler.initialised", redis_host=host, redis_port=port)

    return _scheduler
