from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .engine import GameError
from .room_manager import RoomManager, parse_cards

app = FastAPI(title="Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = RoomManager()


async def broadcast_room(room) -> None:
    stale = []
    for pid, ws in room.sockets.items():
        try:
            await ws.send_json({"type": "state", **room.public_state(pid)})
        except Exception:
            stale.append(pid)
    for pid in stale:
        room.sockets.pop(pid, None)
        p = room.player(pid)
        if p:
            p.connected = False


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    room = None
    player = None

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")

            try:
                if mtype == "create_room":
                    room, player = manager.create_room(msg.get("name", "Игрок"))
                    room.sockets[player.id] = websocket
                    await websocket.send_json({
                        "type": "joined", "room": room.code, "player_id": player.id, "host_id": room.host_id,
                    })
                    await broadcast_room(room)

                elif mtype == "join_room":
                    room, player = manager.join_room(msg.get("room", ""), msg.get("name", "Игрок"))
                    room.sockets[player.id] = websocket
                    await websocket.send_json({
                        "type": "joined", "room": room.code, "player_id": player.id, "host_id": room.host_id,
                    })
                    await broadcast_room(room)

                elif mtype == "rejoin":
                    result = manager.rejoin(msg.get("room", ""), msg.get("player_id", ""))
                    if result is None:
                        await websocket.send_json({"type": "error", "message": "не удалось переподключиться"})
                        continue
                    room, player = result
                    room.sockets[player.id] = websocket
                    await websocket.send_json({
                        "type": "joined", "room": room.code, "player_id": player.id, "host_id": room.host_id,
                    })
                    await broadcast_room(room)

                elif mtype == "start_game":
                    if room is None or player is None:
                        raise GameError("вы не в комнате")
                    room.start_game(player.id)
                    await broadcast_room(room)

                elif mtype == "play_cards":
                    if room is None or player is None or room.engine is None:
                        raise GameError("игра ещё не началась")
                    cards = parse_cards(msg.get("cards", []))
                    room.engine.play_cards(player.id, cards)
                    await broadcast_room(room)

                elif mtype == "draw_card":
                    if room is None or player is None or room.engine is None:
                        raise GameError("игра ещё не началась")
                    room.engine.draw_card(player.id)
                    await broadcast_room(room)

                elif mtype == "pass_turn":
                    if room is None or player is None or room.engine is None:
                        raise GameError("игра ещё не началась")
                    room.engine.pass_turn(player.id)
                    await broadcast_room(room)

                elif mtype == "declare_suit":
                    if room is None or player is None or room.engine is None:
                        raise GameError("игра ещё не началась")
                    room.engine.declare_suit(player.id, msg.get("suit", ""))
                    await broadcast_room(room)

                elif mtype == "declare_bridge":
                    if room is None or player is None or room.engine is None:
                        raise GameError("игра ещё не началась")
                    room.engine.declare_bridge(player.id, bool(msg.get("accept")))
                    await broadcast_room(room)

                elif mtype == "jack_end_choice":
                    if room is None or player is None or room.engine is None:
                        raise GameError("игра ещё не началась")
                    room.engine.resolve_jack_end(player.id, msg.get("choice", ""))
                    await broadcast_room(room)

                elif mtype == "continue_round":
                    if room is None or player is None or room.engine is None:
                        raise GameError("игра ещё не началась")
                    room.engine.continue_round(player.id)
                    await broadcast_room(room)

                elif mtype == "leave_room":
                    if room is not None and player is not None:
                        left_room = room
                        manager.leave_room(room, player.id)
                        room, player = None, None
                        await websocket.send_json({"type": "left"})
                        await broadcast_room(left_room)

                else:
                    await websocket.send_json({"type": "error", "message": f"неизвестное сообщение: {mtype}"})

            except GameError as e:
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        if room is not None and player is not None:
            room.sockets.pop(player.id, None)
            player.connected = False
            await broadcast_room(room)


# In production (Docker) the built frontend is served by this same process, so
# one container handles both the page and /ws. Mounted last so the /ws route
# above takes priority. In dev the folder usually doesn't exist and Vite serves
# the frontend instead.
STATIC_DIR = Path(os.environ.get("BRIDGE_STATIC_DIR", Path(__file__).resolve().parent.parent / "frontend" / "dist"))
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
