import asyncio
import logging
from datetime import datetime, UTC
from typing import Dict, Optional

logger = logging.getLogger("odin.security.permissions")

APPROVAL_TIMEOUT_SECONDS = 300  # 5 minutes


class PermissionManager:
    """Manages pending permission requests.

    Coordinates between the agent (which requests approval) and the API
    (which receives user decisions). This is the single source of truth for
    authorization - the frontend never bypasses this.
    """

    def __init__(self) -> None:
        self._pending: Dict[str, asyncio.Future] = {}

    async def request_approval(self, request_id: str) -> bool:
        """Block the agent until the user approves or denies.

        Returns True if approved, False if denied or timed out.
        Must NEVER be bypassable from the frontend directly.
        """
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        logger.info(f"Waiting for user approval: {request_id}")

        try:
            result: bool = await asyncio.wait_for(
                asyncio.shield(future), timeout=APPROVAL_TIMEOUT_SECONDS
            )
            logger.info(f"Permission {request_id} resolved: {'approved' if result else 'denied'}")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Permission {request_id} timed out after {APPROVAL_TIMEOUT_SECONDS}s")
            self._pending.pop(request_id, None)
            return False
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, request_id: str, approved: bool) -> bool:
        """Resolve a pending permission request from the API route.

        Returns True if the request was found and resolved, False if not found.
        This is called by the API route ONLY after validating the request exists in the DB.
        """
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(approved)
            logger.info(f"Permission {request_id} set to: {'approved' if approved else 'denied'}")
            return True
        logger.warning(f"No pending permission found for: {request_id}")
        return False

    def has_pending(self, request_id: str) -> bool:
        return request_id in self._pending

    def list_pending_ids(self) -> list[str]:
        return list(self._pending.keys())


# Singleton instance shared across the application
permission_manager = PermissionManager()
