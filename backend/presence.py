"""Which accounts are connected right now, and a way to reach them.

A user may have several sockets (two tabs, a phone and a laptop); they count
as online while at least one is open. Like the rooms, this lives in the one
worker process's memory.
"""
from __future__ import annotations

from fastapi import WebSocket

_sockets: dict[int, set[WebSocket]] = {}


def is_online(user_id: int) -> bool:
    return bool(_sockets.get(user_id))


def add(user_id: int, ws: WebSocket) -> bool:
    """Register a socket; True if the user has just come online."""
    sockets = _sockets.setdefault(user_id, set())
    came_online = not sockets
    sockets.add(ws)
    return came_online


def remove(user_id: int, ws: WebSocket) -> bool:
    """Forget a socket; True if that was the user's last one."""
    sockets = _sockets.get(user_id)
    if not sockets or ws not in sockets:
        return False
    sockets.discard(ws)
    if sockets:
        return False
    del _sockets[user_id]
    return True


async def send(user_id: int, message: dict) -> None:
    for ws in list(_sockets.get(user_id, ())):
        try:
            await ws.send_json(message)
        except Exception:
            # a dead socket is dropped when its handler sees the disconnect
            pass
