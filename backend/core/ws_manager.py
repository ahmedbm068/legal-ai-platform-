"""In-process WebSocket connection manager for case message threads.

Connections are grouped into "rooms" keyed by ``case_id``. Both staff and
portal sockets join the same room for a case, so a message sent by either
side is pushed to everyone watching that conversation.

This is intentionally in-process (single worker). For multi-worker /
multi-process deployments this would need a Redis (or similar) pub/sub
backplane; the public API here (:meth:`broadcast`) is shaped so that swap
is localized to this module.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class CaseRoomManager:
    def __init__(self) -> None:
        # case_id -> set of live sockets
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, case_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms[case_id].add(websocket)

    async def disconnect(self, case_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            room = self._rooms.get(case_id)
            if room is not None:
                room.discard(websocket)
                if not room:
                    self._rooms.pop(case_id, None)

    async def broadcast(
        self,
        case_id: int,
        event: dict[str, Any],
        *,
        exclude: WebSocket | None = None,
    ) -> None:
        """Send ``event`` (JSON-serializable) to every socket in the room.

        Dead sockets are pruned. Safe to call from request handlers.
        """
        async with self._lock:
            targets = list(self._rooms.get(case_id, ()))

        if not targets:
            return

        dead: list[WebSocket] = []
        for ws in targets:
            if ws is exclude:
                continue
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                room = self._rooms.get(case_id)
                if room is not None:
                    for ws in dead:
                        room.discard(ws)
                    if not room:
                        self._rooms.pop(case_id, None)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the main event loop (called once at app startup)."""
        self._loop = loop

    def broadcast_threadsafe(self, case_id: int, event: dict[str, Any]) -> None:
        """Schedule a broadcast from sync code (e.g. a REST handler).

        FastAPI runs sync endpoints in a threadpool, so there is no running
        loop in this thread; we hand the coroutine to the captured main loop.
        Fails silently if the loop isn't available yet.
        """
        loop = getattr(self, "_loop", None)
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(case_id, event), loop)
        except Exception:
            pass


# Single shared instance for the process.
room_manager = CaseRoomManager()
