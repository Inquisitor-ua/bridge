from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import auth, bot, db, friends, presence, stats
from .engine import GameError
from .room_manager import RoomManager, parse_cards

db.init_db()

app = FastAPI(title="Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(stats.router)
app.include_router(friends.router)

manager = RoomManager()
log = logging.getLogger(__name__)


INVITE_COOLDOWN = 15.0  # seconds between two invites from one user to the same friend
invite_sent_at: dict[tuple[int, int], float] = {}


async def notify_friends(user_id: int) -> None:
    """A user came online or went offline: their friends' lists show that."""
    for fid in friends.friend_ids(user_id):
        await presence.send(fid, friends.CHANGED)


def player_identity(token: str | None, fallback_name: str) -> tuple[str, int | None, str | None, str | None]:
    """Name, account id, avatar and login for a player joining a room: a
    logged-in user plays under their profile, a guest under whatever they
    typed."""
    user = auth.user_by_token(token)
    if user is None:
        return fallback_name, None, None, None
    return user["display_name"], user["id"], auth.avatar_url(user), user["username"]


async def broadcast_room(room) -> None:
    # every state change ends in a broadcast, so this is the one place that
    # sees a game finish, however it finished (last round, players leaving)
    stats.record_game(room.engine)
    stale = []
    # snapshot: a socket may be added/removed by another connection while we
    # await a send below
    for pid, ws in list(room.sockets.items()):
        try:
            await ws.send_json({"type": "state", **room.public_state(pid)})
        except Exception:
            stale.append(pid)
    for pid in stale:
        room.sockets.pop(pid, None)
        p = room.player(pid)
        if p:
            p.connected = False
    wake_bots(room)


# pauses before a computer player moves, so people can follow what it did
BOT_MOVE_DELAY = (0.9, 1.6)  # seconds, a random value in between
BOT_PROMPT_DELAY = 1.0  # naming a suit, Bridge, the jack ending
BOT_READY_DELAY = 1.2  # "next round" / "new game"
BOT_DEAL_DELAY = 3.5  # a fresh deal: the client is still animating it


def bot_delay(room) -> float:
    eng = room.engine
    if eng.game_over or eng.awaiting_continue:
        return BOT_READY_DELAY
    deal = (eng, eng.round_number)
    if room.bot_seen_deal != deal:
        room.bot_seen_deal = deal
        return BOT_DEAL_DELAY
    if eng.prompt is not None:
        return BOT_PROMPT_DELAY
    return random.uniform(*BOT_MOVE_DELAY)


def wake_bots(room) -> None:
    """Start moving the room's computer players if the game waits on one.
    Called after every broadcast; does nothing while the bots are already
    running or nobody is at the table to watch them."""
    if room.bot_task is not None and not room.bot_task.done():
        return
    if not room.sockets or room.bot_to_act() is None:
        return
    room.bot_task = asyncio.create_task(drive_bots(room))


async def drive_bots(room) -> None:
    try:
        while manager.get_room(room.code) is room and room.sockets:
            player = room.bot_to_act()
            if player is None:
                return
            await asyncio.sleep(bot_delay(room))
            # a person may have acted (or left) during the pause
            if manager.get_room(room.code) is not room or room.bot_to_act() is not player:
                continue
            action = None
            eng = room.engine
            if not (eng.game_over or eng.awaiting_continue):
                # thinking happens on a copy in a worker thread: the hard
                # bot plays rounds ahead, which shouldn't hold up other rooms
                action = await asyncio.to_thread(bot.decide, *bot.snapshot(eng, player))
                if room.engine is not eng or room.bot_to_act() is not player:
                    continue
            room.bot_step(player, action)
            await broadcast_room(room)
    except Exception:
        log.exception("bot crashed in room %s", room.code)


MAX_EMOTE_LEN = 16


async def broadcast_emote(room, player_id: str, emoji: str) -> None:
    for ws in list(room.sockets.values()):
        try:
            await ws.send_json({"type": "emote", "player_id": player_id, "emoji": emoji})
        except Exception:
            # a dead socket is cleaned up by the next state broadcast
            pass


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    # the auth cookie comes with the handshake; the client reconnects after
    # logging in or out, so it never goes stale within one socket
    auth_token = websocket.cookies.get(auth.COOKIE_NAME)
    account = auth.user_by_token(auth_token)
    if account is not None and presence.add(account["id"], websocket):
        await notify_friends(account["id"])
    room = None
    player = None

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")

            try:
                if mtype == "create_room":
                    room, player = manager.create_room(*player_identity(auth_token, msg.get("name", "Игрок")))
                    room.sockets[player.id] = websocket
                    await websocket.send_json({
                        "type": "joined", "room": room.code, "player_id": player.id, "host_id": room.host_id,
                    })
                    await broadcast_room(room)

                elif mtype == "create_bot_game":
                    try:
                        bot_count = int(msg.get("bots", 1))
                    except (TypeError, ValueError):
                        raise GameError("неверное число ботов")
                    room, player = manager.create_bot_room(
                        *player_identity(auth_token, msg.get("name", "Игрок")), str(msg.get("level", "")), bot_count,
                    )
                    room.sockets[player.id] = websocket
                    await websocket.send_json({
                        "type": "joined", "room": room.code, "player_id": player.id, "host_id": room.host_id,
                    })
                    await broadcast_room(room)

                elif mtype == "join_room":
                    room, player = manager.join_room(msg.get("room", ""), *player_identity(auth_token, msg.get("name", "Игрок")))
                    if player.user_id is not None:
                        # they answered: whoever invited them may call them again at once
                        for key in [k for k in invite_sent_at if k[1] == player.user_id]:
                            del invite_sent_at[key]
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
                    if player.user_id is not None:
                        # pick up an avatar changed while away from the room
                        user = auth.user_by_token(auth_token)
                        if user is not None and user["id"] == player.user_id:
                            player.avatar_url = auth.avatar_url(user)
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

                elif mtype == "rematch":
                    if room is None or player is None:
                        raise GameError("вы не в комнате")
                    room.vote_rematch(player.id)
                    await broadcast_room(room)

                elif mtype == "invite_friend":
                    if room is None or player is None:
                        raise GameError("вы не в комнате")
                    if room.engine is not None:
                        raise GameError("игра уже началась")
                    me = auth.user_by_token(auth_token)
                    if me is None or me["id"] != player.user_id:
                        raise GameError("приглашать друзей можно только из аккаунта")
                    friend = friends.friend_by_username(me["id"], str(msg.get("username", "")))
                    if friend is None:
                        raise GameError("этого игрока нет у вас в друзьях")
                    if any(p.user_id == friend["id"] for p in room.players):
                        raise GameError("друг уже в комнате")
                    if not presence.is_online(friend["id"]):
                        raise GameError("друг сейчас не в сети")
                    key = (me["id"], friend["id"])
                    now = time.monotonic()
                    if now - invite_sent_at.get(key, -INVITE_COOLDOWN) < INVITE_COOLDOWN:
                        raise GameError("приглашение уже отправлено, подождите немного")
                    invite_sent_at[key] = now
                    await presence.send(friend["id"], {
                        "type": "invite",
                        "room": room.code,
                        "from": {"name": player.name, "username": player.username, "avatar_url": player.avatar_url},
                    })
                    await websocket.send_json({"type": "invite_sent", "username": friend["username"]})

                elif mtype == "emote":
                    if room is None or player is None:
                        raise GameError("вы не в комнате")
                    emoji = msg.get("emoji")
                    # the client only draws emoji from its own list, so the
                    # server just relays a short string; spam is dropped silently
                    if isinstance(emoji, str) and 0 < len(emoji) <= MAX_EMOTE_LEN and room.allow_emote(player.id):
                        await broadcast_emote(room, player.id, emoji)

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
    finally:
        if account is not None and presence.remove(account["id"], websocket):
            await notify_friends(account["id"])


# In production (Docker) the built frontend is served by this same process, so
# one container handles both the page and /ws. Mounted last so the /ws and
# /api routes above take priority. In dev the folder usually doesn't exist and
# Vite serves the frontend instead.
STATIC_DIR = Path(os.environ.get("BRIDGE_STATIC_DIR", Path(__file__).resolve().parent.parent / "frontend" / "dist"))
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
