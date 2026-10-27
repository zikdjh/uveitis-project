from __future__ import annotations

import asyncio
import logging

from app.asgi import app
from app.core.config import settings


LOGGER = logging.getLogger("uveitis.analysis_worker")


async def run_forever() -> None:
    service = app.state.analysis_job_service
    while True:
        try:
            result = await asyncio.to_thread(service.run_one)
            if result is None:
                await asyncio.sleep(settings.analysis_worker_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("analysis worker iteration failed")
            await asyncio.sleep(settings.analysis_worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
