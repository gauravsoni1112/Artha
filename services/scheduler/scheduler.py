"""
APScheduler setup for Artha.

Uses AsyncIOScheduler (in-process, no extra worker processes).
Jobs are stored in-memory; they are re-registered at every startup
(replace_existing=True), so persistence across restarts is not needed.

Note: RedisJobStore was removed because it pickle-serialises bound methods,
which fails when those methods capture a SQLAlchemy engine (the engine
contains unpicklable closures from create_async_engine).

Usage:
    from services.scheduler.scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.start()
    # Register jobs:
    scheduler.add_job(my_job, "cron", hour=6, minute=0, id="gmail_ingest")
"""

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import structlog

log = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return the singleton AsyncIOScheduler instance."""
    global _scheduler
    if _scheduler is None:
        jobstores = {
            "default": MemoryJobStore(),
        }
        executors = {
            "default": AsyncIOExecutor(),
        }
        job_defaults = {
            "coalesce": True,            # run only once if missed multiple times
            "max_instances": 1,          # never run the same job concurrently
            "misfire_grace_time": 3600,  # tolerate up to 1hr of missed time
        }
        _scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )
        log.info("scheduler.initialised")

    return _scheduler
