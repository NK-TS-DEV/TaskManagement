import asyncio
import logging

from app.core.database import async_session_maker
from app.modules.tasks.services import cancel_overdue_tasks

logger = logging.getLogger(__name__)

OVERDUE_CHECK_INTERVAL_SECONDS = 60


async def _overdue_tasks_worker(interval_seconds: int = OVERDUE_CHECK_INTERVAL_SECONDS) -> None:
    while True:
        try:
            async with async_session_maker() as session:
                cancelled_count = await cancel_overdue_tasks(session)
                if cancelled_count:
                    logger.info("Cancelled %s overdue task(s)", cancelled_count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error while processing overdue tasks in background")

        await asyncio.sleep(interval_seconds)


class BackgroundTasksManager:
    def __init__(self, interval_seconds: int = OVERDUE_CHECK_INTERVAL_SECONDS) -> None:
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                _overdue_tasks_worker(self._interval_seconds)
            )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


background_tasks_manager = BackgroundTasksManager()