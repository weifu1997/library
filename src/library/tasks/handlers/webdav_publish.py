from __future__ import annotations

from typing import Any, Mapping

from library.services.webdav_sync import publish_snapshot
from library.tasks.kinds import KIND_WEBDAV_PUBLISH, task_handler


@task_handler(KIND_WEBDAV_PUBLISH)
async def handle_webdav_publish(payload: Mapping[str, Any]) -> None:
    await publish_snapshot()
